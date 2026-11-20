# GL-1 main board - netlist notes

Stage: **netlist, no copper**. Nothing has been built and nothing is routed. KiCad's DRC has
seen only the board WITHOUT tracks (stage `unrouted`: land patterns, courtyards, keep-outs,
edge distances; 0 errors, every connection still open): that is not the DRC of a routed board.
The part positions in `gl1_main_design.py` are a nominal, legal placement that exists only
because the checks need one; the layout step owns them.

**Revision E (E-EVT1).** The netlist and the routed board implement DESIGN_SPEC rev E: the
amendments E1 to E28 and E35 (E36 is the cradle board). Section 12 says what revision E
changed in this package; where sections 1 to 11 still describe the rev D state, section 12 and
the generated tables are the current state.

The first netlist implemented DESIGN_SPEC rev D with the amendments E1 to E16. The ones that
change the netlist: E1 (charger TI BQ25101 with a hardware thermistor input; the MCP73831, its
PROG MOSFET and its gate divider are gone), E2 (two cell thermistors, Murata NCU15XH103F60RC),
E3 (named LED parts), E4 (four top-side test points), and the stated order of the seven
underside pads. E6 is the cradle board (`../gl1_cradle/CRADLE_NOTES.md`).

This is the netlist **after two independent reviews** (circuit, and conformance with the
specification and the mechanical model). Section 10 lists what changed and what the reviews
found that the netlist could not settle at the time: one mechanical contract that was not met
(J1, section 5.1), one workaround for another package's check (section 5.2), and three things
only the specification's owner could change (charger input headroom, VDDUSB before VDD with a
dead cell, the series diode; section 8). All five are closed at revision E: E24 is in the YAML,
the mechanical check handles copper-only footprints, and E25 / E26 are in the netlist
(sections 11 and 12).

Evidence levels used below, in the design file and in the BOM column "Design evidence" (the
BOM column "Status" is a different thing since revision E: the sourcing status of the part
number, VERIFIED or PROVISIONAL as `docs/SOURCING.md` defines them; section 12):

- **RESEARCH** - seen in `docs/research/*.md` with status "confirmed". Not the manufacturer's datasheet.
- **PINDATA** - read from ST's open pin data (`STM32U585RITx.xml`, `GPIO-STM32U5x_gpio_v1_0_Modes.xml`), re-checked by `check_pinmap.py` on every run.
- **PROVISIONAL** - engineering memory or a web-search extract. No datasheet was read for this work. Every number marked PROVISIONAL must be checked against the datasheet before boards are ordered.

## 1. What is here and how to run it

| File | What it is |
|---|---|
| `gl1_main_design.py` | the netlist as code: parts, nets, net classes, footprints, pin map, mechanical contract (read from `design/master_params.yaml`), nominal placement |
| `check_pinmap.py` | proof of the pin map against ST's open pin data; exports `pinmap.json`; `--selftest` seeds 20 defects and requires each to be caught |
| `pinmap.json` | the final pin map (signal, port pin, pad, mode, AF, pull, initial state, source, reason), with the verification result and the notes for the firmware |
| `check_netlist_rules.py` | DESIGN_SPEC section 4, rule by rule, tested against the netlist, and the pin tables of the library-backed parts against the installed KiCad symbols; `--selftest` seeds 46 defects |
| `netlist_stage.py`, `build_netlist.py` | runner: toolchain checks, rule table, pin map, schematic with netlist round trip, KiCad DRC of the board without tracks, exports |
| `update_notes.py` | fills the generated tables of this file from the design (`--check` fails if one is stale) |
| `netlist_out/` | results of the last run: `checks.txt`, `spec_rules.md`, `pinmap_check.txt`, schematic sheets + PDF, `unrouted/` (board file without tracks and `drc.json`), `gl1_main-netlist.json`, `gl1_main-bom-status.csv`, `gl1_main-nominal-mechanical.json`, `netlist_summary.json` |

Run from `greenline-marker/` (the pin data directory is outside the repository; see `check_pinmap.py`):

    /usr/bin/python3 -B electrical/gl1_main/build_netlist.py --pindata <dir with the two ST files>

Exit status 0 only if no stage failed. Without `--pindata` the pin map is checked against
the installed KiCad symbol only and the result is reported as PARTIAL. Exit status 0 does
**not** mean that nothing is open: the closing lines of the run and `netlist_summary.json`
(`open_items`, `rules.open_not_met`, `rules.workarounds`, `rules.departures`) name the rows
that are not a plain pass.

Content of the netlist:

<!-- BEGIN GENERATED: SUMMARY -->
121 parts: 104 on the BOM (103 fitted, 1 not fitted), 11 bare-copper footprints (BT1, BT2, FL1, FL2, FL3, J2, TP1, TP2, TP3, TP4, TP5), 6 fiducials; 95 nets
<!-- END GENERATED: SUMMARY -->

17 pins are unconnected on purpose: 5 unused balls per camera, the spare element of RN3 and
RN6 (two pins each), U8 pin 4, U4 pins 10 and 11.

## 2. Specification rule -> where it is in the netlist

One row per statement of DESIGN_SPEC section 4 (rail table, the rules in the order they
appear, the PCB paragraph). The table is generated by `check_netlist_rules.py` from the
netlist; every row is a test that ran. The pin-map rule ("the netlist may change proposed
pins; the netlist then wins and exports the final map") is section 3.

A row has one of five results. **pass**: implemented as written. **departure**: the test
passes, but the sentence is implemented differently from its letter (section 5). **open**: a
contract that is NOT met and cannot be met inside this package; the row measures it
(section 5.1). **workaround**: something done to get past a gap in another package (section
5.2). **FAIL**: the netlist is not what the row describes. Only FAIL makes the run exit 1.

<!-- BEGIN GENERATED: RULE_COUNTS -->
**66 rows: 62 as specified; 4 departures from the letter of the spec (section 5): cam 2d, grain c, grain d, PCB c; 0 open - NOT met (section 5.1); 0 workaround (section 5.2); 0 failed.**
<!-- END GENERATED: RULE_COUNTS -->

<!-- BEGIN GENERATED: RULES -->
| Rule | What DESIGN_SPEC section 4 says | Where it is in the netlist | Result |
|---|---|---|---|
| rail VBUS a | VBUS: cradle pad, 5 V; USBLC6-2SC6 clamps VBUS, D+, D- | net VBUS = J2.VBUS (pad 1), U10.VBUS, U12.VIN, C28, R15; USB_DM / USB_DP through U10 pins 1+6 / 3+4 *(ADDED: C28 100 nF at the VBUS pin of U10)* | pass |
| rail VBUS b | E25 (replaces 'Series Schottky from pad to charger'): an ideal-diode switch (TI LM66100DCKR, SC-70-6, enable pin tied to its output so that it blocks reverse current; wiring PROVISIONAL until the data sheet is read) | U12 (LM66100DCKR, SC-70-6): VIN on VBUS (the pad side), VOUT and CE on VBUS_D, GND to GND, ST open; U9.IN on VBUS_D; no Schottky (D17) and no B0530WS left; every pin of U12 comes from the table LM66100_PINS (VIN 1, GND 2, CE 3, NC 4, ST 5, VOUT 6) *(the pin table of U12 is PROVISIONAL (from memory, no second source in the KiCad library): a wrong table mis-wires the switch; that the switch is on while CE is below VIN is from memory too)* | pass |
| rail VBUS c | VBUS loads: BQ25101 IN, VBUS-sense divider | R15 / R16 (100k : 100k) from VBUS (the pad net) to VBUS_SENSE (PC13, WKUP2); U9.IN behind the ideal-diode switch: net VBUS_D = U12.VOUT, U12.CE, U9.IN, C26, U11.IN, C22 *(the divider values are this netlist's choice (the spec gives none))* | pass |
| rail VBAT a | VBAT: cell + PCM; loads MCP1700-2.8 in, LP5907 in, battery divider | net VBAT = BT1, U9.OUT, U7.VIN, U8.IN, R17, C20, C24, C27, TP1 | pass |
| rail VBAT b | 2 x 1 Mohm divider with 100 nF to an ADC pin | R17 / R18 1M, C29 100n on VBAT_SENSE = PA2 (ADC1_IN7) | pass |
| rail VBAT c | The grain LEDs are driven from MCU pins on the 2.8 V rail, not from VBAT | every LED pin is on CP0..CP4; each CPn reaches only its 68 ohm resistor and LEDs | pass |
| rail V2V8 a | V2V8 from MCP1700T-2802E/TT; 1 uF in, 1 uF out ceramic | U7: VIN VBAT (C20 1u), VOUT V2V8 (C21 1u) | pass |
| rail V2V8 b | Loads: MCU VDD / VDDA / VBAT pin, IMU, LCD VDD / VDDA, flash | U1 pads 19, 32, 64, 1; VDDA through R1; U4.VDD, U4.VDDIO; J1.VDD, J1.VDDA; U6.VCC *(ADDED: C13 (flash), C30 / C31 (IMU) 100 nF, C32 1 uF at J1)* | pass |
| rail V2V8 c | 100 nF per MCU supply pin plus 4.7 uF bulk | C1, C2, C3 (VDD), C4 (VBAT), C9 (VDDUSB) 100n; C5 4u7 on V2V8; C6 4u7 on VCAP *(ADDED: C6 on VCAP - not in the spec, needed by the internal regulator; value PROVISIONAL)* | pass |
| rail V2V8 d | VDDA through 10 ohm with 1 uF + 10 nF | R1 10R from V2V8 to VDDA; C7 1u, C8 10n; U1.VDDA pad 13, VSSA to GND | pass |
| rail VDDUSB | E26 (replaces the MCP1700T-3302E/TT of the rail table): TI LP5907MFX-3.3/NOPB, enabled by the 2.8 V rail; fed from VBUS_D (behind the series switch); MCU VDDUSB pin only; 2.2 uF in, 2.2 uF out (E27) | U11 (LP5907MFX-3.3/NOPB, SOT-23-5): IN VBUS_D (C22 2u2), OUT VDDUSB (C23 2u2), EN on V2V8, pad 4 open; net VDDUSB = U1 pad 48, U11.OUT, C9, C23, TP5 (test pad, added) *(2.2 uF in and out is the letter of the rev E rail table (E27; it was a departure from rev D's 1 uF); the DC-bias curves behind E27 are PROVISIONAL. With EN on V2V8 the USB supply pin cannot rise before the main supply (E26). PROVISIONAL, from memory: the enable pin of the LP5907 has an internal pull-down of about 1 Mohm, which draws about 2.8 uA from the always-on rail - it counts against the 25 uA sleep limit of E14 (NETLIST_NOTES 11))* | pass |
| rail V2V8_CAM a | LP5907MFX-2.8/NOPB, EN from MCU with 100k pull-down; 1 uF in, 1 uF out | U8: IN VBAT (C24), OUT V2V8_CAM (C25), EN = CAM_EN (PH0) with R10 100k to GND | pass |
| rail V2V8_CAM b | Loads: both camera AVDD and DOVDD; camera DVDD pin: 1 uF to ground each | U2 / U3 AVDD, DOVDD on V2V8_CAM; C16, C19 1u on CAM_L_DVDD / CAM_R_DVDD *(ADDED: C14, C15, C17, C18 100 nF at the AVDD / DOVDD balls)* | pass |
| cam 1 | SCCB pull-ups (2.2 kohm) go to V2V8_CAM, not V2V8 | R6 (CAM_SCL_L), R7 (CAM_SCL_R), R8 (CAM_SDA) to V2V8_CAM *('driven low or analog while the rail is off' is a firmware rule; every camera-facing pin is a GPIO or a DCMI / MCO pin that can be set analog)* | pass |
| cam 2a | The two cameras share the 8 data lines, PCLK, HREF and VSYNC; every camera output joins the shared bus through a 220 ohm series resistor placed at that camera (three 4-element 0402-in-0804 arrays per camera, Panasonic EXB-28V221JX) | RN1-RN3 at U2, RN4-RN6 at U3: camera pin - A side, bus (CAM_D0..7, CAM_PCLK, CAM_HREF, CAM_VSYNC) - B side, element by element as in the tables CAM_ARRAY_MAP, one per camera (free for the layout step); the 12th element of each camera is unconnected; placement: every array within 2.0 mm of its camera body | pass |
| cam 2b | Each camera has its own SCCB clock line and its own PWDN line; SCCB data is shared | CAM_SCL_L (PC3) - U2.SIOC, CAM_SCL_R (PC0) - U3.SIOC, CAM_SDA (PC1) - both SIOD | pass |
| cam 2c | XVCLK has a 33 ohm series resistor at the MCU | R9 33R between MCO (PA8) and CAM_XVCLK (both XVCLK balls) *(placement: R9 is 2.0 mm from pad 41; nothing fits between the MCU and the battery, the layout step moves it as close as it can)* | pass |
| cam 2d | Each PWDN line has a 1 kohm series resistor and must not use PA9, PA2 or PC10 | R4 1k: PC2 - U2.PWDN; R5 1k: PH3 - U3.PWDN *(DEVIATION: the right camera's PWDN shares the BOOT0 pad (R2 10k to ground is on its MCU side))* | **departure** |
| cam 3 | XVCLK comes from the MCU MCO pin (PA8) | net MCO on U1 pad 41 (RCC_MCO, AF0) *(12 MHz is a firmware setting)* | pass |
| cam 4 | DCMI pin assignment on LQFP-64; SPI1 MISO for the flash must be PB4 | PINMAP rows marked SPEC; check_pinmap.py section E parses the spec text | pass |
| usb | USB: PA11 = D-, PA12 = D+, crystal-less; VDDUSB from its own 3.3 V regulator | USB_DM / USB_DP to J2 pads 2 / 3 through U10; no high-speed crystal in the netlist; U11 | pass |
| lcd a | LCD: SPI clock and data plus an active-high chip select; DISP on a GPIO with pull-down; EXTCOMIN from LPTIM1 or LPTIM3, for example LPTIM1_CH1 on PB2; EXTMODE tied high | J1: SCLK SPI1_SCK (PB3), SI SPI1_MOSI (PB5), SCS LCD_SCS (PB10), EXTCOMIN PB2, DISP LCD_DISP (PB12), VDD / VDDA / EXTMODE V2V8, VSS / VSSA GND | pass |
| lcd b | J1 is a TOP-contact connector (Hirose FH12A-10S-0.5SH(55), 2.0 mm high, on the FH12 land pattern); pin order 1 SCLK 2 SI 3 SCS 4 EXTCOMIN 5 DISP 6 VDDA 7 VDD 8 EXTMODE 9 VSS 10 VSSA | J1 FH12A-10S-0.5SH(55) on the KiCad FH12-10S land pattern, 2.0 mm; LCD_TAIL (tail pin -> function) is that order; every function is on exactly one pad *(the spec's pin order is the order on the TAIL (PROVISIONAL there); which pad a tail pin meets is row lcd c)* | pass |
| lcd c | the LCD tail makes one U-fold under the glass, which turns its contacts upward. Which end of the tail is pin 1 is PROVISIONAL and must be read from the Sharp drawing: a wrong guess mirrors all ten pins | LCD_TAIL_PIN1_EDGE = 'left' (seen from the front, tail up; source: inference from public designs (docs/research/bom-verification-opto.md 3.1)), rear exit, 1 fold about x: tail pin 1 enters J1 at +x; measured on the placed J1: mouth toward -y, pad 1 at x = -2.25, pad 10 at +2.25 - tail pin n is on pad 11 - n (SCLK pad 10 at x = +2.25, VSSA pad 1) *(PROVISIONAL (release gate B16): the pin-1 edge is an inference from public designs (research), not the Sharp drawing; the row proves that the pad table follows from it and that the edge is the one the stated source gives, not that it is right)* | pass |
| imu | IMU on its own SPI bus; INT1 (latched) to a wake-capable pin, INT2 to a second GPIO | SPI2_SCK / MOSI / MISO (PB13 / PB15 / PB14) and IMU_CS (PB1) connect U1 and U4 only; INT1 PA7 (WKUP8), INT2 PA5 *(that PA7 is a wake-up pin is proven by check_pinmap.py)* | pass |
| flash | (section 3) SPI NOR flash on SPI1 with the LCD; MISO on PB4 | U6 MX25R6435F: CS PA10, SO PB4, SI PB5, SCLK PB3; WP# and HOLD# tied to V2V8 | pass |
| clocks | No high-speed crystal | PH0 / PH1 are GPIO (CAM_PWR_EN, CHG_INHIBIT); the only crystal is Y1 | pass |
| grain a | 16 LEDs charlieplexed on 5 MCU pins with one series resistor per pin (5 x 68 ohm), red and NIR LED of each pair antiparallel where possible | R23-R27 68R on PA9, PB0, PC12, PD2, PC10; D1-D16: 8 antiparallel red / NIR pairs on 8 of the 10 line pairs (GRAIN_PAIRS = the firmware's table) | pass |
| grain b | Parts (E3): red Vishay VLMS1500-GS08 (0402); near-infrared ams OSRAM SFH 4053B (0402), alternative Inolux IN-S42CTQIR | D1, D3, ... D15: VLMS1500-GS08; D2, D4, ... D16: SFH 4053B (the alternative is named in the part description) | pass |
| grain c | (YAML) eight LED pairs on a 5.2 mm radius about (0, -4), first at 22.5 degrees, 45 degrees apart, on the underside; red anode on the lower line (firmware table) | D(2k+1) red, D(2k+2) NIR at azimuth 22.5 + 45 k, 0.5 mm either side of the ring point; measured on the pads: inner pad = lower line, outer pad = higher line for all 16 *(DEVIATION: 1.00 mm between the two LEDs of a pair (mechanical model 0.90): two KiCad 0402 courtyards need 0.95)* | **departure** |
| grain d | Photodiode cathode to the op-amp inverting input, 470 kohm + 10 pF feedback, non-inverting input at a mid-rail bias from a 2 x 100 kohm divider with 100 nF | PD1.K, R28 470k, C33 10p on PD_K = PA1 (OPAMP1_VINM); other ends on OPAMP_OUT = PA3; R29 (from LCD_DISP) / R30 100k, C34 100n on VBIAS = PA0 (OPAMP1_VINP); PD1.A to GND *(DEVIATION: the spec names neither the anode net nor the rail of the divider: anode to GND, divider fed from the LCD_DISP line so that it draws nothing asleep. ADDED: R31 150k from PA3 to V2V8 (PA3 is the ROM's USART2_RX))* | **departure** |
| E1 a | Charger: TI BQ25101YFP (4.20 V, DSBGA-6, 0.4 mm ball pitch, all six balls on the perimeter); the ball map is PROVISIONAL and is kept in one marked table | U9 BQ25101YFPR on a generated 2 x 3 land pattern, 0.4 mm pitch; every pin of U9 comes from the table BQ25101_BALLS (OUT A1, IN A2, TS B1, ISET B2, CHG C1, VSS C2) | pass |
| E1 b | IN from VBUS_D, behind the ideal-diode switch U12 (E25), with 2.2 uF; OUT to the cell with 2.2 uF (E27) | U9.IN on VBUS_D with C26 2u2; U9.OUT on VBAT (BT1) with C27 2u2; U9.VSS to GND *(2.2 uF at IN and OUT is the letter of the rev E spec (E27; it was a departure from rev D's 1 uF; the DC-bias curves are PROVISIONAL). Headroom of the charger input with the switch of E25: NETLIST_NOTES 4.1 / 11 (all numbers PROVISIONAL))* | pass |
| E1 c | ISET resistor 6.81 kohm 1 % to ground (K = 135 A-ohm, so 19.8 mA) | R11 6k81 from CHG_ISET (U9.ISET) to GND: 135 / 6810 = 19.82 mA | pass |
| E1 d | TS to a 10 kohm NTC at the cell | RT1 from CHG_TS (U9.TS) to GND; the only other thing on CHG_TS is the drain of Q1 | pass |
| E1 e | CHG (open drain, low while charging) to an MCU input with a 100 kohm pull-up to V2V8 | CHG_STAT = U9.CHG, PA15, R13 100k to V2V8 (and the unfitted R14) | pass |
| E1 f | Firmware stop: CHG_INHIBIT is an MCU push-pull output to the gate of a small N-MOSFET (for example onsemi BSS138, gate pulled down with 100 kohm) that pulls TS to ground | Q1 BSS138: gate CHG_INHIBIT (PH1) with R12 100k to GND, drain CHG_TS, source GND | pass |
| E1 g | Fallback on the same footprint: BQ25100YFP ... the board carries an unpopulated resistor position from that ball to ground for it | R14 (0402, NOT FITTED) from CHG_STAT (ball C1) to GND *(value 6k04 (10 % termination, 20 % pre-charge) is PROVISIONAL; with the BQ25100 fitted R13 must be left out)* | pass |
| E1 h | (E1) the MCP73831, its PROG MOSFET circuit and its gate divider are gone | no MCP73831, no 1N4148 on the status line, no net CHG_PROG*, no part on VBUS_D but the charger, the VDDUSB regulator and their capacitors | pass |
| E2 a | Two 10 kohm NTCs (Murata NCU15XH103F60RC, 0402, B 3380 K) on the top side within 1 mm of the cell edge | RT1, RT2: NCU15XH103F60RC, top side; placement RT1 0.33 mm, RT2 0.33 mm from the cell body *(the dab of thermal adhesive is an assembly step)* | pass |
| E2 b | NTC1 goes from the charger TS ball to ground and belongs to the charger alone | RT1: CHG_TS - GND; no MCU pin on CHG_TS | pass |
| E2 c | NTC2 is the MCU's: divider with 10.0 kohm 1 % from a GPIO (NTC_BIAS, driven only while measuring) to an ADC pin (NTC_SENSE) | R19 10k: NTC_BIAS (PC5) - NTC_SENSE (PC4, ADC1_IN13); RT2: NTC_SENSE - GND; nothing else on either net | pass |
| reset | 100 kohm pull-down on the LCD chip select and on DISP; 100 kohm pull-ups to V2V8 on the flash and IMU chip selects | R21 (LCD_SCS), R22 (LCD_DISP) to GND; R3 (FLASH_CS), R20 (IMU_CS) to V2V8 *(LCD_DISP also carries the top of the grain bias divider (R29 + R30 = 200k more to ground))* | pass |
| crystal | 32.768 kHz crystal on PC14 / PC15: Abracon ABS07-120-32.768KHZ-T with load capacitors sized for 6 pF | Y1 between OSC32_IN (PC14) and OSC32_OUT (PC15); C11, C12 6p8 to GND | pass |
| boot nrst | BOOT0 (PH3) pulled down with 10 kohm; NRST with 100 nF | R2 10k from PH3 (net CAM_R_PWDN_MCU) to GND; C10 100n on NRST | pass |
| pads | Test and service pads on the underside: VBUS, D-, D+, GND, SWDIO, SWCLK, NRST, in that order from x = -7.62 to +7.62 mm seen from above | J2 (bottom side): pad positions measured on the placed footprint, x = [-7.62, -5.08, -2.54, 0.0, 2.54, 5.08, 7.62], y = -17.0; nets left to right ['VBUS', 'USB_DM', 'USB_DP', 'GND', 'SWDIO', 'SWCLK', 'NRST'] *(seen from below with the visor away, VBUS is on the right: the same statement mirrored)* | pass |
| E4 | Test points on the top side (E4), 1.0 mm bare round pads reachable by spring probes before the unit is closed: VBAT, V2V8, V2V8_CAM, GND | TP1 VBAT, TP2 V2V8, TP3 V2V8_CAM, TP4 GND, and ADDED TP5 VDDUSB (E14 gives that rail a board-test limit): round dia 1.0 pads on F.Cu, mask open, no paste *(board test powers the board through BT1 / BT2 (the cell-lead pads))* | pass |
| imu area | No copper pours or vias under the IMU body on the top layer; keep it away from the charger and regulators | rule area under_U4 on F.Cu (tracks, vias, pours); placement: U4 to U9 26.2 mm, to U8 23.7, to U7 12.3, to U11 12.8 mm *('away' has no number in the spec: the test uses this file's own floor of 2.5 mm between bodies (the YAML's nominal part list has 2.85 mm between U4 and U8); the layout step owns the distances)* | pass |
| PCB a | 4 layers, 0.8 mm, D-shaped outline (radius 21.1 mm, flat at y = 17.3 mm) | Design: layers 4, thickness 0.8, PathShape.d_shape from the YAML *(ENIG is the toolchain's stack-up default, written by the fabrication outputs of the layout step)* | pass |
| PCB b | two non-plated locating holes at (14.35, 10.8) and (-14.35, 10.8, a 1.15 x 2.2 mm slot along x) | outline hole H1 dia 1.15 and NPTH slot | pass |
| PCB c | through vias only, 0.25 mm drill, default 0.15 mm tracks with 0.127 mm clearance; E35: the 0.100 / 0.100 mm fine class may be used on F.Cu, In2.Cu and B.Cu inside two rule areas that extend 5 mm beyond each camera ball field, everywhere else 0.15 / 0.127 mm; E7 / E35: fabricator acceptance of 0.100 mm on all three layers is a release gate, the quote request names them | rules GL1_4L_0.10mm; classes Default 0.15 / 0.127, Fine 0.10 / 0.10 and CamPower 0.15 / 0.10 (31 nets, each with a camera ball); two fine areas, pad field of U2 / U3 + 5/5 mm (YAML pcb.net_classes.fine: 0.1 / 0.1 on F.Cu, In2.Cu, B.Cu, 5.0 mm); the fab note on E7 / E35 names F.Cu, In2.Cu and B.Cu *(DEVIATION: CamPower (0.15 / 0.10) is a second class with the fine clearance for the camera supply balls, confined to the same areas)* | **departure** |
| PCB d | provisional 5 x 5 footprint, 0.5 mm pitch, 0.20 mm pads | camera_footprint(): 25 round pads 0.20 mm on 0.5 mm, pad clearance 0.10 (OVM7692_BALLS) | pass |
| PCB e | Vias tented and plugged on the underside, and no via at all inside the grain opening or the pad slot | via_tenting 'both' (the top side is tented too: the cell lies on it), via_protection text; rule areas grain_opening_no_via, pad_slot_no_via and a second area 0.1 mm larger round each | pass |
| PCB f | Layer 2 solid ground | plane GND on In1.Cu (whole board, not routable) *(In2.Cu: V2V8 plane that is also a routing layer - the layout step may change this)* | pass |
| PCB g | no part taller than 2.55 mm anywhere (cameras excepted), six 1.6 mm and two 2.2 mm post-foot keep-outs, nothing taller than 0.95 mm under each camera hood except the camera, nothing taller than 0.7 mm under the LCD flex tail behind the connector | 8 placement keep-outs post_foot_*; height limits free_height, camera_hood_U2 / U3, lcd_tail | pass |
| PCB h | no soldered part above a ball foot or within 0.3 mm of its zone; under each ball foot the bottom side has a 2.5 mm circle with no via and no track and an unmasked 1.6 mm copper land | foot_zone_n_top (placement, dia 2.5 + 2 x 0.3), foot_zone_n (B.Cu: no track, no via, no pour), FL1-FL3: bare dia 1.6 pads WITHOUT a net (mask open, no paste) | pass |
| PCB i | Two solder pads for the cell leads sit in the strip beyond the protection-board end of the cell | BT1 (+, VBAT), BT2 (-, GND): 1.5 x 2.4 pads inside battery.pads.zone | pass |
| PCB j | Parts on the top side except the grain LEDs, photodiode and contact pads | bottom side: D1-D16, PD1 (fitted), J2, FL1-FL3, three fiducials (bare copper) | pass |
| PCB k | The cameras, the LCD connector and the battery are fixed mechanical interfaces | U2, U3: body boxes equal the YAML boxes; battery_body placement keep-out from the YAML; J1: at the position E24 and the rev E YAML give (row PCB k2) | pass |
| PCB k2 | E24: J1 moves 0.5 mm toward the rear: mouth at y = -17.30, body to y = -11.70, signal pads end at y = -10.40 (0.20 mm clear of the cell at y = -10.20); the tail-fold zone starts at the mouth. Rev E YAML: top_side_parts J1 body box 8.1 x 5.6 centred on (0.0, -14.5), anchor (0.0, -12.9), mouth_y -17.3, pads_end_y -10.4; battery.board_keepout_notch x [-5.55, 5.55], y [-10.2, -9.9] | measured on the placed land pattern: anchor (0.00, -12.90), body x -4.05 to 4.05, y -17.30 to -11.70 (rear face = mouth), signal pads y -11.70 to -10.40, cell edge -10.20, courtyard to -9.90; 0.00 mm2 of the body inside the YAML's LCD-tail zone (y -21.1 to -17.3, which starts at the mouth). Battery keep-out: the YAML box of the cell less a notch 11.10 x 0.30 mm = the YAML notch *(the courtyard of the land pattern (0.5 mm beyond the pad ends) reaches 0.30 mm into the YAML box of the cell: the placement keep-out has the notch the YAML records for it; body and pads are outside the cell. No departure since rev E)* | pass |
| PCB l | (YAML pcb.component_edge_clearance) part bodies stay 0.2 mm inside the board edge | smallest distance from a part body to the board edge: 0.225 mm (U2), then 0.225 mm (U3) | pass |
| pin tables | (task) the pin -> pad table of every library-backed part agrees with a second source | U7, U11, U8, U10, Q1, U6, U4 against the installed KiCad symbols (pad numbers, pin names, footprint); D1-D16 against KiCad's pad 1 = cathode; RN1-RN6 against element n = pads n and 9 - n: all agree *(U6 is compared with the MX25R3235F of the same family and package, U4 with the LSM6DSM (spec: pin-compatible); U1 is proven by check_pinmap.py; U2 / U3, U9, U12, PD1 and J1 have no second source: their tables are the PROVISIONAL ones)* | pass |
| bare copper | (mechanical/cad/board_import.py, rev E) a copper-only footprint is one with zero height and no BOM line; it is tested by its own rules and a 'not fitted' mark does not exempt it; a zero-height component with a BOM line fails | 17 copper-only footprints (zero height, no BOM line): BT1, BT2, FID1, FID2, FID3, FID4, FID5, FID6, FL1, FL2, FL3, J2, TP1, TP2, TP3, TP4, TP5; none of them carries a 'not fitted' mark (none); FL1-FL3 and the three bottom fiducials are board-only footprints with one netless pad; no BOM part has zero height (none) | pass |
| fiducials | (task) at least three global fiducials per side | FID1-FID3 top, FID4-FID6 bottom | pass |
| E5 | Assembly (E5): lead-free (SAC305) reflow, RoHS-compliant parts; no conformal coating | fab note; no leaded part is named in the BOM | pass |
| status | (task) every BOM part carries an evidence status | Part.fields['Status'] is RESEARCH or PROVISIONAL on all 104 BOM parts | pass |
<!-- END GENERATED: RULES -->

Parts of the rules that are firmware, test or process matters and cannot be seen in a netlist:
camera-facing pins low or analog while V2V8_CAM is off, one camera driving at a time, 12 MHz
on MCO, HSI48 with clock recovery, 32768 / 547 for EXTCOMIN, the thermal adhesive on the two
NTCs, the board-test limits of E14 (2.8 V +-3 %, 3.3 V +-3 %, sleep current no more than
25 uA at 3.8 V through the cell-lead pads), ENIG.

## 3. Pin map

### 3.1 What `check_pinmap.py` proves

| Section | Claim | Source |
|---|---|---|
| A | the 64 pads of U1: pad number and pin name equal the package | PINDATA |
| B | every row: the pad, and the alternate function with its AF number or the analog function exists on that pin | PINDATA |
| C | IMU_INT1 (PA7, WKUP8) and VBUS_SENSE (PC13, WKUP2) are wake-up pins on different wake-up lines; EXTI lines used once each (5, 7, 13, 15); ADC channels exist (PA2 IN7, PC4 IN13, PA3 IN8); OPAMP1 pins are PA0 / PA1 / PA3 and are the only pads with those functions | PINDATA |
| D | no pin used twice (52 rows on 51 pads: PH3 is the declared BOOT0 + CAM_R_PWDN pair); no I/O pad connected without a row; the 13 supply and reset pads are on their nets | netlist |
| E | the 16 assignments fixed by the spec text (parsed from DESIGN_SPEC.md) are unchanged; PWDN not on PA9 / PA2 / PC10 and through 1 kohm; XVCLK through 33 ohm; SCCB pull-ups to V2V8_CAM; the BOOT0 pad has 10 kohm to ground, no path to another rail and no output on its net | spec + netlist |
| F | difference to `firmware/hal/stm32u5/gl_pins.h`; every change has a reason | header |
| G | every pin the ROM bootloader drives or listens on: what is connected and why it does not react badly; CAM_PWR_EN and CHG_INHIBIT are on no bootloader pin | **PROVISIONAL** pin list (memory of ST AN2606, not readable here; a web-search extract of a third-party copy agrees for USART1-3, I2C1-3, SPI1, FDCAN1); each function's existence on its pin is PINDATA |
| H | second source: the installed KiCad symbol agrees | KiCad library |
| I | the two UCPD1 CC pads (PA15, PB15) and their dead-battery control pads (PB5, PB14), found in the pin data, carry only signals from an allow-list with a stated reason: an input, or an alternate-function output into CMOS inputs; never an LED line or a signal that switches power. The pad with USB_OTG_FS_VBUS (PA9) is named in the notes for the firmware | which pads: PINDATA; what they do: **PROVISIONAL** (section 3.6) |

All 51 I/O pads carry a signal. **There is no spare MCU pin**: 51 signals and the BOOT0 strap
share 51 pads, so one signal has to sit on the BOOT0 pad (3.4).

### 3.2 The map

U1 is assumed at rotation 270 deg (pads 1-16 on the edge that faces the cameras, 17-32 on the
left, 33-48 toward the battery, 49-64 on the right): the orientation of the toolchain demo and
of the YAML's nominal part list. The proposed pins were chosen for that orientation: camera
control on pads 5, 8-11 and 60, IMU on 21, 23, 27 and 34-36, flash on 43 and 55-57, LCD on
28, 29, 33, grain LEDs on 26, 42, 51, 53 and 54, the charger on 6 and 50, the NTC on 24 and 25. "Pull" is internal / external.

<!-- BEGIN GENERATED: PIN_TABLE -->
| Pad | Pin | Signal | Net | Mode | Function | Pull (MCU / board) | Initial state | Source |
|---|---|---|---|---|---|---|---|---|
| 2 | PC13 | VBUS_SENSE | VBUS_SENSE | EXTI | GPIO (PWR_WKUP2) | none / divider 100k : 100k from VBUS | input | CHANGED (was PA9) |
| 3 | PC14 | OSC32_IN | OSC32_IN | ANALOG | RCC_OSC32_IN | none | LSE | SPEC |
| 4 | PC15 | OSC32_OUT | OSC32_OUT | ANALOG | RCC_OSC32_OUT | none | LSE | SPEC |
| 5 | PH0 | CAM_PWR_EN | CAM_EN | OUT_PP | GPIO | none / 100k to GND | low (rail off) | CHANGED (was PD2) |
| 6 | PH1 | CHG_INHIBIT | CHG_INHIBIT | OUT_PP | GPIO | none / 100k to GND | analog or low: charger on (its hardware default) | PROPOSED |
| 8 | PC0 | CAM_R_SCL | CAM_SCL_R | SCCB_OD | GPIO | none / 2k2 to V2V8_CAM | low or analog while V2V8_CAM is off | CHANGED (was PA10) |
| 9 | PC1 | CAM_SCCB_SDA | CAM_SDA | SCCB_OD | GPIO | none / 2k2 to V2V8_CAM | low or analog while V2V8_CAM is off | CHANGED (was PB5) |
| 10 | PC2 | CAM_L_PWDN | CAM_L_PWDN_MCU | OUT_PP | GPIO | none / 1k series | low or analog while V2V8_CAM is off | CHANGED (was PH0) |
| 11 | PC3 | CAM_L_SCL | CAM_SCL_L | SCCB_OD | GPIO | none / 2k2 to V2V8_CAM | low or analog while V2V8_CAM is off | CHANGED (was PB3) |
| 14 | PA0 | OPAMP_VINP | VBIAS | ANALOG | OPAMP1_VINP | none | analog | SPEC |
| 15 | PA1 | OPAMP_VINM | PD_K | ANALOG | OPAMP1_VINM | none | analog | SPEC |
| 16 | PA2 | VBAT_SENSE | VBAT_SENSE | ANALOG | ADC1_IN7 | none | analog | PROPOSED |
| 17 | PA3 | OPAMP_VOUT | OPAMP_OUT | ANALOG | OPAMP1_VOUT / ADC1_IN8 | none / 150k to V2V8 | analog | SPEC |
| 20 | PA4 | CAM_HREF | CAM_HREF | AF | DCMI_HSYNC (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 21 | PA5 | IMU_INT2 | IMU_INT2 | EXTI | GPIO | none | input | CHANGED (was PC5) |
| 22 | PA6 | CAM_PIXCLK | CAM_PCLK | AF | DCMI_PIXCLK (AF4) | none | low or analog while V2V8_CAM is off | SPEC |
| 23 | PA7 | IMU_INT1 | IMU_INT1 | EXTI | GPIO (PWR_WKUP8) | none | input | CHANGED (was PC13) |
| 24 | PC4 | NTC_SENSE | NTC_SENSE | ANALOG | ADC1_IN13 | none | analog | PROPOSED |
| 25 | PC5 | NTC_BIAS | NTC_BIAS | OUT_PP | GPIO | none | analog; high only during an NTC conversion | CHANGED (was PH3) |
| 26 | PB0 | GRAIN_CP1 | CP1_MCU | OUT_PP | GPIO | none / 68R series | analog (no LED lit) | CHANGED (was PC1) |
| 27 | PB1 | IMU_CS | IMU_CS | OUT_PP | GPIO | none / 100k to V2V8 | high (not selected) | CHANGED (was PB12) |
| 28 | PB2 | LCD_EXTCOMIN | LCD_EXTCOMIN | AF | LPTIM1_CH1 (AF1) | none | low until LPTIM1 runs | SPEC |
| 29 | PB10 | LCD_SCS | LCD_SCS | OUT_PP | GPIO | none / 100k to GND | low (not selected) | PROPOSED |
| 33 | PB12 | LCD_DISP | LCD_DISP | OUT_PP | GPIO | none / 100k to GND (and 200k: grain bias divider) | low (display off) | CHANGED (was PB1) |
| 34 | PB13 | SPI2_SCK | SPI2_SCK | AF | SPI2_SCK (AF5) | none | low | PROPOSED |
| 35 | PB14 | SPI2_MISO | SPI2_MISO | AF | SPI2_MISO (AF5) | none | input | PROPOSED |
| 36 | PB15 | SPI2_MOSI | SPI2_MOSI | AF | SPI2_MOSI (AF5) | none | low | PROPOSED |
| 37 | PC6 | CAM_D0 | CAM_D0 | AF | DCMI_D0 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 38 | PC7 | CAM_D1 | CAM_D1 | AF | DCMI_D1 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 39 | PC8 | CAM_D2 | CAM_D2 | AF | DCMI_D2 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 40 | PC9 | CAM_D3 | CAM_D3 | AF | DCMI_D3 (AF4) | none | low or analog while V2V8_CAM is off | SPEC |
| 41 | PA8 | CAM_XVCLK | MCO | AF | RCC_MCO (AF0) | none | low or analog while V2V8_CAM is off | SPEC |
| 42 | PA9 | GRAIN_CP0 | CP0_MCU | OUT_PP | GPIO | none / 68R series | analog (no LED lit) | CHANGED (was PC0) |
| 43 | PA10 | FLASH_CS | FLASH_CS | OUT_PP | GPIO | none / 100k to V2V8 | high (not selected) | CHANGED (was PA15) |
| 44 | PA11 | USB_DM | USB_DM | AF | USB_OTG_FS_DM (AF10) | none | analog until USB starts | SPEC |
| 45 | PA12 | USB_DP | USB_DP | AF | USB_OTG_FS_DP (AF10) | none | analog until USB starts | SPEC |
| 46 | PA13 | SWDIO | SWDIO | AF | DEBUG_JTMS-SWDIO (AF0) | reset state (pull-up) | reset state | SPEC |
| 49 | PA14 | SWCLK | SWCLK | AF | DEBUG_JTCK-SWCLK (AF0) | reset state (pull-down) | reset state | SPEC |
| 50 | PA15 | CHG_STAT | CHG_STAT | EXTI | GPIO | none / 100k to V2V8 | input | CHANGED (was PB0) |
| 51 | PC10 | GRAIN_CP4 | CP4_MCU | OUT_PP | GPIO | none / 68R series | analog (no LED lit) | PROPOSED |
| 52 | PC11 | CAM_D4 | CAM_D4 | AF | DCMI_D4 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 53 | PC12 | GRAIN_CP2 | CP2_MCU | OUT_PP | GPIO | none / 68R series | analog (no LED lit) | CHANGED (was PC2) |
| 54 | PD2 | GRAIN_CP3 | CP3_MCU | OUT_PP | GPIO | none / 68R series | analog (no LED lit) | CHANGED (was PC3) |
| 55 | PB3 | SPI1_SCK | SPI1_SCK | AF | SPI1_SCK (AF5) | none | low | CHANGED (was PA5) |
| 56 | PB4 | SPI1_MISO | SPI1_MISO | AF | SPI1_MISO (AF5) | none | input | SPEC |
| 57 | PB5 | SPI1_MOSI | SPI1_MOSI | AF | SPI1_MOSI (AF5) | none | low | CHANGED (was PA7) |
| 58 | PB6 | CAM_D5 | CAM_D5 | AF | DCMI_D5 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 59 | PB7 | CAM_VSYNC | CAM_VSYNC | AF | DCMI_VSYNC (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 60 | PH3 | BOOT0 | CAM_R_PWDN_MCU | STRAP | BOOT0 | 10k to GND | low at reset | SPEC |
| 60 | PH3 | CAM_R_PWDN | CAM_R_PWDN_MCU | OUT_PP | GPIO | none / 10k to GND (BOOT0), 1k series | low or analog while V2V8_CAM is off | CHANGED (was PC12) |
| 61 | PB8 | CAM_D6 | CAM_D6 | AF | DCMI_D6 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
| 62 | PB9 | CAM_D7 | CAM_D7 | AF | DCMI_D7 (AF10) | none | low or analog while V2V8_CAM is off | SPEC |
<!-- END GENERATED: PIN_TABLE -->

Supply and reset pads: 1 VBAT, 19, 32, 64 VDD on V2V8; 13 VDDA; 12 VSSA, 18, 31, 47, 63 VSS on
GND; 30 VCAP; 48 VDDUSB; 7 NRST.

### 3.3 Pins changed from `gl_pins.h`

<!-- BEGIN GENERATED: PIN_COUNTS -->
52 rows: 24 SPEC, 8 PROPOSED (unchanged), 20 CHANGED. Unchanged PROPOSED pins: CHG_INHIBIT, GRAIN_CP4, LCD_SCS, NTC_SENSE, SPI2_MISO, SPI2_MOSI, SPI2_SCK, VBAT_SENSE.
<!-- END GENERATED: PIN_COUNTS -->

<!-- BEGIN GENERATED: CHANGED_TABLE -->
| Signal | gl_pins.h | Netlist | Reason |
|---|---|---|---|
| CAM_L_PWDN | PH0 | PC2 (pad 10) | PC2 sits next to CAM_L_SCL on the camera-facing edge; PH0 takes CAM_PWR_EN |
| CAM_L_SCL | PB3 | PC3 (pad 11) | PB3 is needed for SPI1_SCK next to the flash; PC3 is the left end of the camera-facing edge |
| CAM_PWR_EN | PD2 | PH0 (pad 5) | camera-facing edge; a static signal is the right neighbour for OSC32_OUT (pad 4); PD2 goes to the grain LEDs |
| CAM_R_PWDN | PC12 | PH3 (pad 60) | the BOOT0 pad must carry one signal (51 signals, 51 I/O pads). PWDN of the right camera suits it: the pad is on the edge next to that camera, the net has no pull-up (BOOT0 stays low at every reset) and a static output does not mind the 10k; the firmware's proposal, NTC_BIAS, would be loaded by it |
| CAM_R_SCL | PA10 | PC0 (pad 8) | PA10 is on the battery-facing edge; PC0 faces the cameras, PA10 takes FLASH_CS |
| CAM_SCCB_SDA | PB5 | PC1 (pad 9) | PB5 is needed for SPI1_MOSI next to the flash; PC1 is in the middle of the camera-facing edge |
| CHG_STAT | PB0 | PA15 (pad 50) | exchanged with GRAIN_CP1 (see there). An INPUT is what the UCPD1_CC1 pad can carry whatever its output stage is: its reset state (JTDI, internal pull-up) agrees with the 100 kohm pull-up, and a dead-battery pull-down before firmware sets UCPD_DBDIS only makes the line read 'charging' while nobody reads it |
| FLASH_CS | PA15 | PA10 (pad 43) | PA10 is the ROM bootloader's USART1_RX: a pulled-up chip select is exactly the idle level it wants there, a floating charlieplex line is not. PA15 is no place for a chip select either: it is the UCPD1_CC1 pad, which gets a 5.1 kohm pull-down while PB5 (SPI1_MOSI, floating in reset) is high (PROVISIONAL) |
| GRAIN_CP0 | PC0 | PA9 (pad 42) | PC0-PC3 face the cameras and carry SCCB / PWDN now; PA9, PC10, PC12, PD2 are the corner next to the LED ring |
| GRAIN_CP1 | PC1 | PB0 (pad 26) | PC1 carries SCCB data now. The free pad at the LED corner, PA15, is the UCPD1_CC1 pad (PINDATA): a 5.1 kohm dead-battery pull-down appears on it while PB5 is high until firmware sets UCPD_DBDIS, and its output stage may be weaker than an ordinary pad's (ST's FT_c structure; both PROVISIONAL, DS13086 not read). Line 1 lights 8 of the 16 LEDs at 5 to 10 mA, so it sits on an ordinary pad instead: PB0, the nearest one with no ROM bootloader function, exchanged with CHG_STAT |
| GRAIN_CP2 | PC2 | PC12 (pad 53) | see GRAIN_CP0 |
| GRAIN_CP3 | PC3 | PD2 (pad 54) | see GRAIN_CP0 |
| IMU_CS | PB12 | PB1 (pad 27) | PB12 is the ROM bootloader's SPI2 chip-select input and PB14 its SPI2 data output, wired to the IMU's SDO. If the ROM enables a pull-down on PB12 (the remembered AN2606 text says it does), the 100k pull-up loses, the IMU is selected and its SDO fights PB14. On PB1 (left edge, next to the IMU, no bootloader function) the pull-up always wins and SDO stays high-impedance |
| IMU_INT1 | PC13 | PA7 (pad 23) | PA7 faces the IMU and is a wake-up pin (WKUP8); PC13 is on the far corner next to the crystal and takes VBUS_SENSE |
| IMU_INT2 | PC5 | PA5 (pad 21) | PA5 faces the IMU. PA5 / PA7 are the ROM bootloader's SPI1 clock and data inputs: with both driven by the IMU they always have a defined level; PC5 takes NTC_BIAS |
| LCD_DISP | PB1 | PB12 (pad 33) | exchanged with IMU_CS (see there): a line with a pull-DOWN is what the ROM bootloader's SPI2 chip-select input can carry without harm; pad 33 is on the way down to J1 |
| NTC_BIAS | PH3 | PC5 (pad 25) | PH3 carries the 10k BOOT0 pull-down, which would load the ratiometric bias (0.28 mA more through the pin's output resistance, up to 0.4 K at 0 C); PC5 is the pad next to NTC_SENSE and no ROM bootloader pin |
| SPI1_MOSI | PA7 | PB5 (pad 57) | see SPI1_SCK |
| SPI1_SCK | PA5 | PB3 (pad 55) | PB3 / PB4 / PB5 are three adjacent pads on the edge that faces the flash; PA5 is on the opposite edge |
| VBUS_SENSE | PA9 | PC13 (pad 2) | PA9 goes to the grain LEDs; PC13 is a wake-up pin, so the cradle can wake the marker from Shutdown (ship mode, E13), and a static signal is the right neighbour for OSC32_IN (pad 3); PC13 may only sink 3 mA: it is an input here |
<!-- END GENERATED: CHANGED_TABLE -->

Two rows change their meaning with E1 (`gl_pins.h` has not been regenerated since):
**CHG_INHIBIT** (PH1, same pin) is now a push-pull output, HIGH = stop charging (gate of Q1);
it was an open-drain line, LOW = stop. The firmware as it stands (`drivers/power.c`,
`inhibit_()`: latch low, then open drain) therefore does nothing on this board: its own charge
gate is inoperative until that function drives the pin high. **CHG_STAT** (now PA15) is the
open-drain CHG output of the BQ25101 with 100 kohm to V2V8; it was the STAT output of the
MCP73831 on PB0. CHG_PROG_EN does not exist.

### 3.4 The BOOT0 pad

PH3 is sampled as BOOT0 at reset and is an ordinary I/O afterwards. A signal can share it only
if nothing on its net can lift the pad at reset. Candidates that pass: NTC_BIAS (the
firmware's proposal), CAM_PWR_EN, CHG_INHIBIT and a PWDN line; a line with a pull-up (SCCB,
chip selects, CHG_STAT) cannot (a watchdog reset during a read would boot the ROM), a
charlieplex line would light an LED through the 10 kohm.

The netlist puts **CAM_R_PWDN** there: pad 60 is on the package edge next to the right camera;
the net is R2 (10 kohm to ground), R5 (1 kohm) and the camera's PWDN input, nothing else; a
static output does not mind sourcing 0.28 mA into R2 while it is high (the camera rail is on
then, 86 mA). The firmware's choice, NTC_BIAS, works but puts the 10 kohm across a ratiometric
divider: (73 + 280) uA through an output resistance of up to 50 ohm is 17.7 mV, 0.53 K at 0 C
instead of 0.11 K (PROVISIONAL output resistance). After a reset the node (about 20 pF)
is at ground within a microsecond, long before BOOT0 is sampled. Firmware option: program the
option bits so that the BOOT0 pin is ignored (nSWBOOT0 = 0, nBOOT0 = 1; PROVISIONAL).

### 3.5 ROM bootloader pins (pin list PROVISIONAL)

The bootloader runs only if the flash is empty or firmware jumps to it (there is no BOOT0 pad
on the underside). The camera rail is then off: U8.EN is on PH0 with R10 to ground and PH0 is
not a bootloader pin. The charger stays on: the gate of Q1 is on PH1 with R12 to ground, not
a bootloader pin either.

| Pin, bootloader function | Net | Why it is harmless |
|---|---|---|
| PA9 USART1_TX, PC10 USART3_TX (driven high) | GRAIN_CP0, GRAIN_CP4 | 68 ohm, then LEDs only; an LED needs a second line at low and the bootloader drives none of the five low. The other three lines (PB0, PC12, PD2) have no bootloader function, no reset pull and no UCPD function, so nothing can pull one of them low. No charlieplex line is on a pin the bootloader listens on (such a line would float at an LED forward voltage) |
| PA2 USART2_TX (driven) | VBAT_SENSE | resistor network only (R17, R18, C29): at most 4 uA |
| PA6 SPI1_MISO, PB9 FDCAN1_TX (driven) | CAM_PIXCLK, CAM_D7 | into two unpowered camera pins through 220 ohm each. Bound with the camera rail held at 0 V and a 0.65 V diode: 19.5 mA from the pin (9.8 mA per camera pin); about 6 mA expected. This is the case the spec's 220 ohm resistors exist for; it is above the 8 mA the I/O levels are specified at and just under the 20 mA absolute maximum (both PROVISIONAL) |
| PB14 SPI2_MISO (driven) | SPI2_MISO | U4.SDO only. **IMU_CS is on PB1, not on PB12**: PB12 is the ROM's SPI2 chip-select input, and if the ROM enables a pull-down there (the remembered AN2606 text says it does on its SPI pins) a 100 kohm pull-up loses (0.6 to 1.0 V), the IMU is selected and its SDO fights PB14. On PB1 the pull-up always wins: SDO stays high-impedance (PROVISIONAL) |
| PB12 SPI2_NSS | LCD_DISP | held low by R22; a pull-down of the ROM agrees with it |
| PB13 SPI2_SCK, PB15 SPI2_MOSI | SPI2_SCK, SPI2_MOSI | inputs of the IMU only; nothing on the board drives them. They are held by the ROM's own pull-downs if it enables them (PROVISIONAL); a false sync of the ROM's SPI slave would need the byte 0x5A |
| PA5 SPI1_SCK, PA7 SPI1_MOSI | IMU_INT2, IMU_INT1 | two push-pull outputs of the always-on IMU: defined levels whatever pull the ROM sets. The ROM's SPI slave reacts only to 0x5A on MOSI clocked by eight SCK edges. **Condition for the firmware: leave INT2 static before a jump to the ROM** |
| PA4 SPI1_NSS, PB6, PB7, PB8, PC11 | CAM_HREF, CAM_D5, CAM_VSYNC, CAM_D6, CAM_D4 | end only on unpowered camera outputs: static, no edges (PROVISIONAL: ordinary protection diodes in the OVM7692) |
| PA10 USART1_RX | FLASH_CS | idle high through R3 |
| PA3 USART2_RX | OPAMP_OUT | idle high through R31 (150 kohm, added for this): 2.8 V in the dark, 2.0 V or more with the photodiode saturated by light (4.10) |
| PB10 I2C2_SCL | LCD_SCS | held low by R21, static |
| PC0 I2C3_SCL, PC1 I2C3_SDA | CAM_SCL_R, CAM_SDA | pulled to the unpowered camera rail through 2.2 kohm: static low |
| PA11, PA12 USB | USB_DM, USB_DP | their purpose |

Which pulls the ROM enables is not known. The verdicts hold for "pull-down on SPI pins,
pull-up on USART pins, none on I2C pins" (AN2606 as remembered) and for no pulls at all.

The firmware's generator (`tools/gen_pins.py`) has two rules: it refuses a PROPOSED
camera-facing pin on a pin the bootloader **drives**, and it refuses CHG_INHIBIT, NTC_BIAS and
NTC_SENSE on **any** bootloader pin. The netlist meets both as they are written: the two SCCB
lines on PC0 / PC1 (the ROM's I2C3 pins, which it only listens on) pass the first rule
unchanged. They are open-drain and pulled to a rail that is off, so nothing is driven into an
unpowered camera. The camera-facing package edge has only five pins without any bootloader
function (PC2, PC3, PH0, PH1, PC13); they carry CAM_L_PWDN, CAM_L_SCL, CAM_PWR_EN,
CHG_INHIBIT and VBUS_SENSE.

Reset state of the JTAG pins: PA15 (JTDI, internal pull-up) is CHG_STAT, where the pull-up
agrees with R13, and PB4 (NJTRST, internal pull-up) is SPI1_MISO. Firmware must switch PA15,
PB3, PB4 from JTAG to their functions (SWD only).

### 3.6 The UCPD pads (what they do is PROVISIONAL)

The pin data puts four functions of the USB Type-C port controller on pads this board uses
for something else (check_pinmap section I finds them in the data):

| Pad | UCPD function | Signal here |
|---|---|---|
| PA15 (50) | UCPD1_CC1 | CHG_STAT (input) |
| PB15 (36) | UCPD1_CC2 | SPI2_MOSI |
| PB5 (57) | UCPD1_DBCC1: dead-battery control of CC1 | SPI1_MOSI |
| PB14 (35) | UCPD1_DBCC2: dead-battery control of CC2 | SPI2_MISO |

From memory of ST's reference manual and data sheet (**not read**): after reset the
"dead battery" behaviour is enabled, and a high level on a DBCC pad switches a 5.1 kohm
pull-down onto its CC pad until firmware sets `UCPD_DBDIS` in `PWR_UCPDR`. The two CC pads
are ST's FT_c pad structure; whether their output stage drives 5 to 10 mA like an ordinary
pad's is not known here.

What the netlist does about it, so that it is right whichever way those facts turn out:

- **No LED line on a CC pad.** The first netlist had GRAIN_CP1 on PA15. Line 1 lights 8 of
  the 16 LEDs; a weaker pad would drive them differently from the other eight, and a
  5.1 kohm pull-down on the line (PB5 floats in reset and in the ROM bootloader) leaks
  0.1 to 0.3 mA through LEDs of other azimuths. GRAIN_CP1 is now on PB0, an ordinary pad
  without a bootloader function, and PA15 carries CHG_STAT, an input: a pull-down there
  only makes the line read "charging" (27 uA through R13) while nobody reads it.
- PB15 carries SPI2_MOSI, an alternate-function output into one CMOS input. With PB14 high
  and the bit not set it would cost 2.8 V / 5.1 kohm = 0.55 mA while driven high, 20 times
  the sleep limit: **the firmware must set UCPD_DBDIS before it configures any pin**
  (section 7), and again after every wake-up that resets the PWR registers.
- PA9, GRAIN_CP0, is also USB_OTG_FS_VBUS: the USB device must run with VBUS sensing off.

### 3.7 Lines without a defined level in reset and in the ROM bootloader

The spec asks for pulls on the four chip selects, DISP and the camera rail enable only, and
the netlist has exactly those (plus R12, R13, R2, R31). These inputs of always-powered parts
therefore float from reset until `gl_hal_init()` drives them, and for as long as the ROM
bootloader runs (a firmware update, or a board that was never programmed):

| Line | Floating input | Why no pull was added |
|---|---|---|
| LCD_EXTCOMIN (PB2) | LCD EXTCOMIN | DISP is held low by R22: the panel is off. A pull-down would cost 14 uA while the display runs (50 % duty) |
| SPI1_SCK, SPI1_MOSI (PB3, PB5) | LCD SCLK / SI, flash SCLK / SI | both devices are deselected by R21 and R3 |
| SPI2_SCK, SPI2_MOSI (PB13, PB15) | IMU SCL / SDA | the IMU's CS is high (R20), which is its I2C mode: random levels are not a valid address. If the ROM enables its SPI pull-downs the lines are low |
| CAM_L_PWDN (PC2) | left camera PWDN through R4 | the camera is unpowered in reset; firmware sets PWDN before it switches the rail on. The right camera's line has the BOOT0 resistor R2, the left one has nothing: asymmetric, harmless |

No damage mechanism is known; the cost is some extra supply current of parts whose data
sheets were not read (PROVISIONAL), during a reset or an update. Four 100 kohm pull-downs
(0402) would remove the question; they are **not fitted** because the spec asks for none
and the board has no room to spare. The spec owner may decide otherwise. Firmware: give each
of these lines its level first, and keep internal pull-downs on PB4 and PB14 (the MISO lines
float between transfers).

## 4. Part values and the calculations behind them

V2V8 = 2.8 V. MCU limits used (all PROVISIONAL, datasheet DS13086 not read): input high
0.7 x VDD = 1.96 V, input low 0.3 x VDD = 0.84 V; output levels specified at 8 mA, absolute
maximum 20 mA per pin; output resistance 15-50 ohm (25 typical); input leakage 150 nA worst
case, a few nA at room temperature; internal pulls about 40 kohm (25-55).

### 4.1 Supply chain in the cradle

The marker draws about 30 mA from VBUS: 19.8 mA of charge current (which includes whatever
the system takes from VBAT), up to 1 mA for the charger, up to 8 mA for VDDUSB (USB
transceiver; both PROVISIONAL) and 25 uA for the sense divider. Between the cradle's USB
connector and the charger lie the cable (0.5 ohm), the cradle's fuse (E25: chosen for no
more than 1.5 ohm after a trip; 0.8 ohm taken as typical), two spring-pin contacts and the
ideal-diode switch U12 (E25, TI LM66100: about 0.08 ohm typical, 0.15 ohm taken as worst,
i.e. 2 to 5 mV at 30 mA). **Every one of these numbers is PROVISIONAL** (table
`SUPPLY_CHAIN` in the design file); none was read from a data sheet.

`docs/research/power.md` records the operating input range of the BQ2510x as **4.45 to
6.45 V** (marked UNVERIFIED there). Against that figure:

<!-- BEGIN GENERATED: SUPPLY_CHAIN -->
| Case | USB source | at the VBUS pad | VBUS_D (charger IN, U11 in) | against 4.45 V |
|---|---|---|---|---|
| low limit of a compliant USB source, worst parts | 4.75 V | 4.69 V | 4.68 V | **+0.23 V** |
| low limit of a compliant USB source, typical parts | 4.75 V | 4.71 V | 4.71 V | **+0.26 V** |
| nominal source, worst parts | 5.00 V | 4.94 V | 4.93 V | **+0.48 V** |
| nominal source, typical parts | 5.00 V | 4.96 V | 4.96 V | **+0.51 V** |
| a legacy port that delivers 4.40 V, typical parts | 4.40 V | 4.36 V | 4.36 V | **-0.09 V** |
<!-- END GENERATED: SUPPLY_CHAIN -->

**With the switch of E25 the charger's input keeps 0.23 to 0.26 V above 4.45 V at the low
end of a compliant USB source** (it was 0.08 to 0.22 V BELOW it with the Schottky D17 and
the first fuse; that finding of the netlist review is what E25 answers). A source that
delivers only 4.40 V still leaves the charger 0.09 V short. What the charger does below its
minimum input (stop, charge more slowly, or regulate its input) was not read. To be read in
TI SLUSBV8: the minimum operating input, the input-detection threshold and any input-voltage
regulation; in TI SLVSEZ8 (LM66100): the pin table, the CE comparator (the netlist assumes
"on while CE is below VIN", so CE on VOUT blocks reverse current), the on-resistance at
4.4 V and the behaviour at power-up with VOUT at 0 V.
Proposed board-test item (E14): with 4.75 V at the cradle's USB connector and the charger
in fast charge, measure VBUS_D at C26; limit 4.45 V (PROVISIONAL), expected 4.68 to 4.71 V.

Other nodes: VBUS_D is at most the VBUS pad voltage (5.5 V source maximum). U11
(LP5907-3.3, E26) needs 3.3 V plus its drop-out (about 50 mV at 8 mA, PROVISIONAL) and
takes 5.5 V at most (PROVISIONAL, memory): 4.36 to 5.5 V is inside that, with no margin at
the top - a release-gate reading.

Capacitance on the 5 V side: C28 100 nF at U10 / U12 (pad side), C26 and C22 2.2 uF nominal
at the charger and at U11: 4.5 uF nominal (about 2 uF effective at 5 V, 4.7) behind the
cradle fuse, inside the 1-10 uF a USB device may show. Hot insertion charges them through
the fuse and U12; the LM66100's soft start, if it has one, was not read (PROVISIONAL).

## 5. Departures from the specification

| No. | Spec | Netlist | Why |
|---|---|---|---|
| 1 | "mid-rail bias from a 2 x 100 kohm divider" (rail not named) | divider fed from LCD_DISP (PB12) | 4.10: from V2V8 it would take 14 uA of the 25 uA sleep limit; no pin is free for an enable |
| 2 | photodiode anode not named | to ground | 4.10 |
| 3 | BOOT0 (PH3) pulled down with 10 kohm | PH3 is also CAM_R_PWDN | 3.4: 51 signals on 51 pads; this net has no pull-up and the pad is next to the right camera |
| 4 | (not in the spec) | C6, C13, C14, C15, C17, C18, C28, C30, C31, C32, R31 added; R15 / R16 values chosen | 4.3, 4.6, 4.7, 4.10 |
| 5 | fine class 0.10 / 0.10 for the camera escape (E35: on F.Cu, In2.Cu and B.Cu inside two areas 5 mm beyond each camera ball field) | a second class "CamPower" (0.15 mm track, 0.10 mm clearance) for V2V8_CAM and the two DVDD nets | a supply ball needs the fine clearance to leave the BGA but not the thin track. Both classes are fine only inside the two fine areas round U2 and U3. The fine class on three layers is NOT a departure any more (E35); CamPower still is (it is in no amendment) |
| 6 | "Layer 2 solid ground" | In1.Cu ground, whole board; In2.Cu is a V2V8 plane that may also carry tracks | the spec is silent on layer 3; the layout step decides |
| 7 | proposed pins of `gl_pins.h` | 20 changed, section 3.3 | allowed by the pin-map rule; the firmware header must be regenerated from `pinmap.json` |
| 8 | LED pair as drawn by the mechanical model: 0.90 mm between the two LEDs | 1.00 mm | two KiCad 0402 LED courtyards need 0.95 mm |
| 9 | "unmasked 1.6 mm copper land" under each ball foot | FL1-FL3: pads **without a net** | see below |
| 10 | (rev D) "1 uF in, 1 uF out"; "IN ... with 1 uF; OUT to the cell with 1 uF". **CLOSED at rev E: the spec says 2.2 uF at these four places (E27); rule rows "rail VDDUSB" and "E1 b" quote the rev E text and are passes** | C22, C26 (VBUS_D), C23 (VDDUSB), C27 (charger output): **2.2 uF** nominal, same 0402 footprint | 4.7: a 1 uF 10 V 0402 keeps roughly half of its value at 5 V; with 2.2 uF about 1 uF is left where a regulator or the charger asks for it. PROVISIONAL, no bias curve read |
| 11 | BQ25101YFP | order code BQ25101YFPR (reel; YFPT is the small reel) | suffix seen in the search results; PROVISIONAL |
| 12 | "LCD connector pin order 1 SCLK ... 10 VSSA" | read as the order on the **tail**; tail pin n is on connector pad 11 - n (pad 1 = VSSA, pad 10 = SCLK) | section 6 and rule row "lcd c": with the U-fold and the mouth of J1 to the rear the evidence in the repository says the tail is mirrored against the land pattern. PROVISIONAL (release gate B16) |

| 13 | (rev D) YAML `top_side_parts` J1: box centred on (0, -13.9), mouth at y = -16.8 | **E24**: anchor of the land pattern at (0, -12.90): mouth (rear face of the body) at y = -17.30, body to -11.70, signal pads end at -10.40 | **CLOSED at rev E**: the YAML has the body box centred on (0, -14.5), the anchor, the mouth and the pad ends (5.1) |
| 14 | (rev D) battery-body placement keep-out = the YAML box of the cell | the YAML box less a notch 11.10 x 0.30 mm at its rear edge for J1's courtyard | **CLOSED at rev E**: the notch is the YAML key `battery.board_keepout_notch`; the keep-out is `battery.body` less exactly that (5.1) |
| 15 | E25 / E26 name the parts and the wiring only | U12 (LM66100) ST pin open, pad 4 open; U11 (LP5907-3.3) EN directly on V2V8 | section 11; both pin tables and the EN pull-down current are PROVISIONAL |

The first netlist had the VBUS-sense divider behind the series element; it is now on the pad net,
as the rail table lists it (4.3), and is no departure any more.

**The ball-foot lands are unconnected, not ground.** The contract forbids any track or via
inside the 2.5 mm circle on the bottom side, so a land cannot be tied to anything without
breaking it, and the toolchain does not need a net (a pad without a net is legal). The land
has no electrical job: the ball bears on it through a film of epoxy (YAML: 0.02 mm). Left
floating it also cannot carry current between a wet underside and a supply. One thing for
the layout step: keep In2.Cu (V2V8) copper out from under the three lands, so that the
nearest copper above a land is the ground plane.

Nothing was relaxed, excluded or waived to get a clean report. The rule set is the
toolchain's standard four-layer set with the minimum track and clearance set to the spec's
0.100 mm (E7: 3.94 mil; the fabricator's written acceptance is a release gate and a fab note).

### 5.1 J1: amendment E24, in the YAML since revision E (no departure any more)

Rule rows "PCB k" and "PCB k2" (result **pass**) measure this on every run.

The netlist review found that the rev D YAML's box for J1 (5.8 mm deep, mouth at y = -16.8,
the cell at y = -10.2) left 6.60 mm for a land pattern that needs 6.90 mm from the rear face
of its body to the ends of its signal pads. **E24 decided it**: J1 moved 0.5 mm toward the
rear. Revision E of the YAML carries it: `top_side_parts` J1 has the BODY box (x, y = body
centre (0, -14.5), dx 8.1, dy 5.6), `anchor` (0, -12.9), `mouth_y` -17.3, `body_y`
(-17.3, -11.7) and `pads_end_y` -10.4. On the board (measured on the placed KiCad
`Hirose_FH12-10S-0.5SH` footprint):

| | y (mm) | YAML key |
|---|---|---|
| footprint anchor | -12.90 | `anchor` |
| rear face of the body = mouth | -17.30 | `mouth_y`, `body_y[0]` |
| front face of the body | -11.70 | `body_y[1]` |
| signal pads | -11.70 to -10.40 | `pads_end_y` |
| cell edge | -10.20 (0.20 mm from the pad ends) | `battery.board_keepout_notch.pad_to_cell_gap` |
| courtyard of the land pattern | -17.80 to -9.90 | `courtyard` |

- The design file reads the mouth and the pad ends from the YAML and computes the anchor from
  the land pattern (4.40 mm in front of the rear face); row "PCB k2" requires the computed
  anchor to equal the YAML `anchor`, the measured body box to equal the YAML box within
  0.005 mm, and the tail zone to start at the mouth with no part of J1's body in it.
- `mechanical/cad/board_import.py` compares J1's body box and, separately, its anchor with the
  YAML: it passes (it failed on this row at rev D, and the main build then exited 2; that
  special exit status is gone).
- KiCad's courtyard reaches 0.30 mm into the YAML box of the cell. The battery placement
  keep-out is the YAML box less a notch of exactly J1's courtyard width (11.10 mm) and that
  depth; since revision E the notch is the YAML key `battery.board_keepout_notch` (x +-5.55,
  y -10.2 to -9.9, "J1 courtyard only; no copper, solder or body of J1 inside the cell box")
  and the rule row requires the keep-out to be `battery.body` less exactly that notch, J1's
  body to be outside the cell and every J1 pad to keep 0.20 mm from it.
- The YAML's LCD-tail zone is now y -21.1 to -17.3 (parts to 0.7 mm): it starts at the mouth.
  No part stands in it. Tail length and fold stay PROVISIONAL (Sharp drawing, release gate
  B16); the mechanical model has one fold of radius 0.99 mm behind the mouth, not proven on a
  real tail.

Seeded defects (all caught): J1 0.7 mm toward the cell; J1's anchor put on the YAML body
centre; J1 back on its rev D position; J1 turned by 180 degrees.

### 5.2 The "not fitted" mark on six bare-copper footprints: REMOVED at revision E

Rule row "bare copper" (result **pass**; it was a **workaround** at rev D).

At rev D `mechanical/cad/board_import.py` (check D) required every fitted bottom-side
component of the board's mechanical JSON to lie inside the grain opening or the pad slot, and
the toolchain's mechanical JSON lists copper-only footprints as components. The three
ball-foot lands FL1-FL3 and the three bottom fiducials FID4-FID6 therefore carried a "not
fitted" mark (`BARE_BOTTOM_COPPER_NOT_FITTED`) that hid them from that check.

Since revision E that check recognises a copper-only footprint by what the file itself says
(body height 0 and no BOM line) and tests it by its own rules: a ball-foot land must sit on a
YAML foot zone within 0.05 mm with dia 1.6, one per foot; other bare bottom copper must lie
outside the grain opening, the pad slot and the foot zones; the "not fitted" mark exempts
nothing, and a zero-height component with a BOM line fails. The flag is gone from the design
file; no footprint without a BOM line carries the mark. The rule row now requires exactly
that (17 copper-only footprints, none marked, no BOM part of zero height), and the self-test
seeds the old workaround on FL2, on FID5 and on test pad TP4: each is caught. On the routed
board the mechanical import reports "14 copper-only footprints by their own rules (3
ball-foot lands on their feet)" and passes.

## 6. PROVISIONAL items

Isolated in one table each in `gl1_main_design.py`, so that each can be corrected in one place:

| Table | What is not known | Effect of an error |
|---|---|---|
| `OVM7692_BALLS`, `OVM7692_PITCH`, `OVM7692_PAD_D` | the whole ball map, the pitch and the pad size of the camera (a stand-in: the spec's "provisional 5 x 5, 0.5 mm, 0.20 mm") | both camera footprints and 31 nets |
| `BQ25101_BALLS`, `BQ25101_PITCH`, `BQ25101_PAD_D`, `BQ25101_BODY` | ball map and land pattern of the charger: from two web-search extracts of TI SLUSBV8C (C1 = CHG / PRE-TERM and C2 = VSS from ti.com's document viewer; the full map from a third-party copy), handedness of the drawing assumed | charger dead or reversed; six nets |
| `LCD_TAIL`, `LCD_TAIL_PIN1_EDGE` (with `LCD_TAIL_FOLDS_ABOUT_X`, `J1_PAD1_X_SIGN_AT_ROT0`) | pin order on the LCD tail, and at which edge of the tail pin 1 is | all ten pins of J1 mirrored |
| `VEMD8080_PADS` | land pattern of the photodiode and which pad is the anode | photodiode reversed or shorted |

**The LCD tail: which way the fold maps.** `LCD_TAIL_PIN1_EDGE = "left"` is the one fact
to read from the Sharp drawing (release gate B16): looking at the front of the display with
the tail pointing up, away from the glass, is tail pin 1 at the left or at the right edge?
"Left" is what the research supports, by inference: the contacts are on the rear face, and a
public design plugs the tail straight into a bottom-contact FH12 on the KiCad land pattern
with pad 1 = SCLK; in that land pattern pad 1 is at x = -2.25 with the mouth toward -y, so
the tail travels +y with pin 1 at -x, the left edge when it points up. In the GL-1 the tail
leaves the rear edge of the glass pointing -y, which puts pin 1 at **+x**; one U-fold about
an axis parallel to x brings it back travelling +y with its contacts up (hence the
top-contact FH12A) and pin 1 still at +x; J1 has its mouth to the rear and pad 1 at
x = -2.25. Tail pin 1 therefore meets **pad 10**: the tail is mirrored against the land
pattern, `LCD_TAIL_PIN1_AT_PAD1` is derived as False, and J1 is wired pad 1 = VSSA ...
pad 10 = SCLK. The one top-contact design the research found is wired in that reverse order
too. The first netlist had the straight order; with it VSSA / VSS would have sat on
SPI1_SCK / SPI1_MOSI and VDD on EXTCOMIN. None of the public designs is confirmed as built,
so this stays PROVISIONAL: if the drawing says "right", change that one word and all ten
pads follow. The spec's sentence "LCD connector pin order: 1 SCLK ... 10 VSSA" should be
reworded as the order on the tail.

Others, by part:

| Item | PROVISIONAL content |
|---|---|
| ROM bootloader | the list of pins it drives or listens on and the pulls it enables (memory of AN2606; one weak search extract); the SPI sync byte (memory of AN4286) |
| U1 electrical | input thresholds, 8 mA / 20 mA output figures, PC13 limited to 3 mA, leakage, output resistance, internal pull values, injection current; VCAP 4.7 uF; OPAMP1 bandwidths; LSE drive limits; option bits; embedded USB resistors; supply sequencing (section 8); the UCPD dead-battery pull-downs, UCPD_DBDIS and the output drive of the FT_c pads PA15 / PB15 (3.6); the VDDUSB monitor |
| U2, U3 | besides the ball map: behaviour of PWDN and of the outputs when unpowered, protection diodes, SCCB address and sink current, decoupling |
| U9 BQ25101 | besides the ball map: K = 135 A-ohm (spec), TS bias current and thresholds, behaviour with TS low (disabled) and TS open (TTDM), termination and pre-charge ratios, **minimum operating input (4.45 V in the research, unverified), input-detection threshold and any input-voltage regulation (4.1)**, input over-voltage threshold, battery leakage, leakage of the CHG pin, output capacitance needed with the cell disconnected, order code; R14 value for the BQ25100 |
| U7, U11 MCP1700 | order codes -2802 and -3302 (from the spec and distributor listings in docs/sourcing.csv), tolerance, 6 V maximum input |
| U8 LP5907 | EN threshold, output discharge resistance (230 ohm assumed in the bootloader estimate) |
| Q1 BSS138 | pin order, threshold, on-resistance at 2.8 V, leakage |
| D17 | forward voltage at 30 mA (0.30 V typical, 0.35 V maximum assumed), reverse leakage |
| D1-D16 | forward voltages, reverse rating; the SFH 4053B data sheet has not been read; the generic KiCad 0402 LED land pattern and its polarity mark |
| Y1 | stray capacitance 2.5 pF, C0, motional capacitance, ESR; the KiCad land pattern is drawn for another maker's 3215 crystal |
| RT1, RT2 | B value and tolerance (no R-T table read), stock |
| U4 | wiring of pins 2 and 3; SDO high impedance when not selected; state of INT1 / INT2 after power-on |
| U6 | height; deep power-down current |
| RN1-RN6 | stock, height, match of the KiCad convex 4 x 0402 land pattern |
| J1 | top-contact FH12A on the FH12 land pattern (spec) and that it numbers its contacts like the FH12 (docs/SOURCING.md A15: check the land pattern and the 2.0 mm height against the Hirose FH12A drawing); the tail fold behind its mouth (5.1); LCD supply range 2.7-3.3 V (2.8 V - 3 % = 2.72 V) |
| passives | every MPN of the 0402 resistors and capacitors is from memory; the capacitance left under DC bias (4.7) |
| J2, BT1, BT2 | pad diameter 1.8 mm (YAML text), pad gap 0.7 mm (mechanical model) |
| U6 | pin 7 is HOLD# or RESET# depending on the family member (tied high: inactive for both) |
| placement | nominal; in it both NTCs are within 0.4 mm of the cell body, RT1 is 2.5 mm from the charger and U8 is 2.9 mm from the IMU |

`netlist_out/gl1_main-bom-status.csv` carries two status columns for every BOM line (section
12): "Status" = the sourcing status of the part number per `docs/SOURCING.md` (37 VERIFIED),
"Design evidence" = the level of the design data (31 PROVISIONAL, 6 RESEARCH). The toolchain's
own BOM has no status column; the design evidence is also in each part's `Status` field.

## 7. Consequences for the firmware

The same list is exported in `pinmap.json` (`firmware_notes`), so that it travels with the
map. Items 2 and 4 are not optional: until they are done the present firmware cannot stop a
charge on this board and does not compile against the regenerated header.

<!-- BEGIN GENERATED: FIRMWARE_NOTES -->
1. Regenerate gl_pins.h from pinmap.json (every row marked CHANGED moved).
2. CHG_INHIBIT (PH1) is a PUSH-PULL output, HIGH = stop charging (it turns on Q1, which pulls the charger's TS input low); analog or low = charger on. drivers/power.c inhibit_() does exactly this since firmware phase 3 (push-pull HIGH to stop, analog to release); with the MCU off or hung only the charger's hardware TS window acts.
3. CHG_STAT is on PA15 (EXTI15): the BQ25101's open-drain CHG output with a 100 kohm pull-up to V2V8, low = charging, high = not charging, done or no VBUS. No internal pull is needed. With the BQ25100 fallback fitted every internal pull on PA15 must be off (it also has the JTDI pull-up until the firmware switches to SWD only).
4. EXTI lines: IMU_INT1 PA7 = EXTI7 (WKUP8), IMU_INT2 PA5 = EXTI5, VBUS_SENSE PC13 = EXTI13 (WKUP2), CHG_STAT PA15 = EXTI15. hal/stm32u5/gl_hal_stm32u5.c builds its vectors and compile-time asserts from the GL_PINS_EXTI_* numbers of the generated header.
5. UCPD (PROVISIONAL, RM0456 / DS13086 not read): PA15 and PB15 are the UCPD1 CC pads, PB5 and PB14 their dead-battery control pads. After reset a high level on PB5 (SPI1_MOSI) switches a 5.1 kohm pull-down onto PA15, a high level on PB14 (SPI2_MISO) one onto PB15 (SPI2_MOSI: 0.55 mA while it is driven high). Set UCPD_DBDIS in PWR_UCPDR (HAL_PWREx_DisableUCPDDeadBattery) at the top of gl_hal_init(), before any pin is configured, and again after every wake-up that resets the PWR registers.
6. PA9 is USB_OTG_FS_VBUS and carries GRAIN_CP0: run the USB device with VBUS sensing off and tell the core that the session is valid from VBUS_SENSE (register details PROVISIONAL).
7. USB supply: set the USB-supply-valid bit only while BOTH VBUS_SENSE (PC13) is high AND the MCU's own VDDUSB monitor reports the supply ready; clear it on the falling edge of either. PC13 alone does not measure VDDUSB: on undocking VDDUSB can fall below 3.0 V within about a millisecond under USB load while PC13 still reads high for up to about 22 ms.
8. VBUS_SENSE: divider 100 kohm : 100 kohm on the VBUS pad (not behind the series switch U12). High is guaranteed above 3.92 V at the pad, low below 1.68 V; removal from the cradle is seen within about 22 ms.
9. CAM_R_PWDN is on PH3, the BOOT0 pad (10 kohm to ground): it reads low at every reset; 0.28 mA flows into the pull-down while it is driven high.
10. IMU_CS is PB1 and LCD_DISP is PB12 (exchanged: PB12 is the ROM bootloader's SPI2 chip-select input).
11. Before a jump to the ROM bootloader leave the IMU with its INT2 output static (data-ready routing off): PA5 / PA7 are the ROM's SPI1 clock and data inputs.
12. The grain bias divider hangs on LCD_DISP (PB12): DISP must have been high for 35 ms before a grain measurement. drivers/grain_frontend.c waits 25 ms after it enables the op-amp and does not look at the display: gl_grain_fe_power() must wait for, or refuse without, 35 ms of display-on time.
13. Switch PA15, PB3, PB4 away from JTAG (SWD only).
14. Every camera-facing pin low or analog while V2V8_CAM is off: PC0, PC1, PC3 (SCCB), PC2, PH3 (PWDN), the eleven DCMI pins and PA8.
15. Lines without a board pull float while the MCU is in reset or in the ROM bootloader: LCD_EXTCOMIN (PB2), SPI1_SCK / SPI1_MOSI (PB3 / PB5), SPI2_SCK / SPI2_MOSI (PB13 / PB15), CAM_L_PWDN (PC2). gl_hal_init() must give each its level before anything else; keep an internal pull-down on PB4 and PB14 (the MISO lines float between transfers; PB14 is also UCPD1_DBCC2).
16. PA3 (OPAMP1 output, the ROM's USART2_RX) is held high by R31, 150 kohm to V2V8, also with light on the photodiode. Leave PA3 analog while OPAMP1 is off: driven low it costs 19 uA.
17. LSE drive: medium-low or higher (NETLIST_NOTES 4.9).
<!-- END GENERATED: FIRMWARE_NOTES -->

Also: charge termination. A marker that is awake in the cradle draws more than the 2 mA
termination current from the charger's output, so the charger may never report "complete"
and holds 4.2 V. Firmware should end the charge itself with CHG_INHIBIT (time and voltage)
and must not rely on CHG_STAT going high.

## 8. For the spec owner, the mechanical owner and the layout step

### 8.1 Three things only the specification can change

- **VDDUSB comes up before VDD when a marker with a dead cell is docked.** U11 is a
  three-pin regulator fed straight from VBUS_D (the spec's rail table). With the cell at its
  protection cut-off V2V8 is 0 V; on docking VDDUSB reaches 3.3 V within about a millisecond
  while VDD follows only after the charger has detected its input and restarted the cell
  node (tens of milliseconds, PROVISIONAL). ST requires VDDUSB (and VDDA, VDDIO2) to stay
  below VDD + 0.3 V while VDD is under 1 V (memory of DS13086, **PROVISIONAL**, not read).
  If that is right, the rule is broken at every such docking, including the first docking
  of a unit that arrives with a tripped protection circuit. The netlist does not change it:
  the rail table names the part and its feed. Proposal for an amendment: make VDDUSB depend
  on V2V8 - a 3.3 V regulator with an enable pin driven from V2V8 (same SOT-23-5 footprint
  class as U8, one resistor), or a small load switch in U11's input gated by V2V8; two more
  parts near U11 at most. Release gate until then: read the power-sequencing paragraph of
  DS13086. The other paths into an unpowered MCU were walked and are benign: VBUS_SENSE
  into PC13 is at most 2.75 V through 50 kohm, CHG is pulled low, not driven, and PA11 /
  PA12 see only the host's pull-downs.
- **Charger input headroom** (4.1): below the 4.45 V the research records at the low end of
  a compliant USB source; spec-inherited (series Schottky plus the cradle fuse).
- **The series diode.** With the charger's 30 V input rating and its reverse blocking (both
  PROVISIONAL) the Schottky's remaining jobs are reverse polarity at the pads and keeping
  the 4.4 uF of VBUS_D off the exposed pad. Whether that is worth 0.3 V is a spec decision.

### 8.2 Observations

- **Open NTC1 defeats the hardware temperature window.** By the search extract a floating TS pin puts the charger into its test mode (no temperature monitoring, no timers, no termination). A cracked joint on RT1 therefore removes the protection E1 exists for, silently. Board test should measure the TS voltage (about 0.5 V at 25 C, PROVISIONAL) at RT1; firmware can cross-check NTC2 against the charger's behaviour. To be confirmed in the data sheet.
- **Exposed NRST pad.** NRST has only the MCU's internal pull-up (about 40 kohm) and 100 nF. A conductive film from the NRST pad to ground below about 17 kohm holds the MCU in reset. The spec asks for no external pull-up; none was added.
- **No ESD parts on SWDIO, SWCLK, NRST** (the spec asks for clamps on VBUS, D+, D- only).
- **Inputs that float in reset and in the ROM bootloader** (3.7): no pull-downs were added; the spec owner may want four.
- **Photodiode with the amplifier off.** In bright light the cathode node (PA1) is pulled below ground by the photodiode itself (to its open-circuit voltage, about 0.4 V) while OPAMP1 is off. The diode limits its own voltage, so the injection into PA1 should stay small; the pin's injection rating was not read. The sleep-current test must be made with the underside dark (4.10).
- **BQ25100 fallback.** Fit R14, leave out R13, and CHG_STAT means nothing (4.2). On PA15 the JTDI pull-up (about 40 kohm, until firmware switches to SWD) then feeds the programming pin in reset and in the ROM bootloader.
- **No spare MCU pin** (section 3.1).
- **`docs/sourcing.csv` and `docs/SOURCING.md`** (revision 4, 2026-11-18; listings as seen on 2026-11-13) list the current charger, NTC and near-infrared LED. Brought into step with this netlist in the final audit of rev E (report revision 4, 2026-11-18): the numbered rows main-01 to main-37 and cradle-01 to cradle-07 are the BOM lines with the BOM's item numbers (U11 LP5907MFX-3.3/NOPB is main-34, U12 LM66100DCKR main-35, F1 0603L035YR cradle-02); D17, the MCP1700-3.3 and the old fuse are history rows. Taken from the sourcing report into the design files after the layout review: the 1 uF and 2.2 uF order codes (actions A1, A2), the order codes of A17, the IMU's distributor and price (A13), the cradle fuse (A5) and the spring-pin tail and hole (A6). The status BOM (`out/assembly/gl1_main-bom-status.csv`) carries the sourcing risk and the alternate candidates of every line (none approved), copied from the row of `docs/sourcing.csv` with the line's references.

### 8.3 Mechanical

- **J1** (5.1): closed at revision E (E24 is in the YAML; the tail fold is the mechanical model's, PROVISIONAL).
- **Bare bottom copper and the mechanical import** (5.2): closed at revision E (`board_import.py` tests copper-only footprints by their own rules and compares J1 by body box and by anchor).
- **The cell against soldered leads.** In the nominal placement the lead pads of U1 (pads 33 to 48) are 0.45 mm from the cell body and its courtyard 0.20 mm. The 13.4 mm courtyard sits between the cell (y -0.2) and the post-foot keep-outs (y 13.75): 0.55 mm of freedom in all, so 0.80 mm from pad copper to the cell is the most any placement can give. No tolerance on the cell's width or position is stated: the mechanical owner should give one.
- **The cell's protection-board end.** The YAML has the protection board at the -x end of the 34 mm body; its length is provisional. An NTC beside that end reads the protection board, not the cell. Both NTCs are over the cell proper in the nominal placement (x = -6.6 and -9.4).
- **LED pair pitch** 1.00 mm against the model's 0.90 mm (section 5, no. 8).

### 8.4 For the layout step

- **Free for the layout step.** Which of the twelve array elements of a camera carries which output is arbitrary: the table `CAM_ARRAY_MAP` in the design file may be permuted to untangle the BGA escape (and must be revisited when the real ball map replaces the stand-in). PROPOSED and CHANGED pins of the pin map may still move; `check_pinmap.py` then says what breaks. **Not** onto PA15 or PB15 with anything but an input or an alternate-function output into CMOS inputs (3.6).
- **J1 is wired mirrored** against the first netlist: SCLK, SI, SCS, EXTCOMIN, DISP are on pads 10 to 6 (x = +2.25 to +0.25), VDDA, VDD, EXTMODE, VSS, VSSA on pads 5 to 1. PROVISIONAL; a correction from the Sharp drawing would mirror them back.
- **Parts that still sit where their old nets were.** R24 (charlieplex line 1) now belongs at pad 26 of U1 (PB0, left edge); line 1 leaves from there, the other four from the corner at pads 42 and 51 to 54. R15 belongs at the VBUS pad end (U10 / D17 / J2 pad 1): the long run to PC13 should be the 100 kohm-limited VBUS_SENSE, not VBUS. CHG_STAT runs from U9 (lower left) to pad 50 (lower right): a static line, any layer.
- **Placement constraints seen on the nominal placement.** U1: see 8.3. RT1 (the charger's NTC) is 2.5 mm from the charger U9, which dissipates up to about 46 mW; aim for 3 mm or more along the cell edge, because a warm NTC1 errs on the unsafe side at the cold limit (the E2 rule itself is met: RT1 0.23 mm, RT2 0.33 mm from the cell). Give the post-foot keep-out squares 0.2 mm to pad copper as well as to bodies (R4, R5, R10, C29 were at 0.18 to 0.19 mm and have been nudged). Camera bodies are 0.225 mm from the flat edge (rule row "PCB l", limit 0.2 mm).
- **Layout.** R9 belongs at pad 41 of U1 and the six arrays at the cameras (spec); nothing fits between the MCU and the battery, so R9 sits at a corner of the package. Keep U8, U9, U7, U11 away from U4. Keep V2V8 copper on In2.Cu out from under the foot lands (section 5). The three inner LED runs and the two photodiode nets leave the ring on the bottom layer between the LED pairs. If the VDDUSB amendment of 8.1 is adopted, two more small parts are needed beside U11.
- **The nominal placement is not a layout.** Two informational runs of the toolchain's router on the first netlist's placement (scratch directory, not part of this stage; 540 s with the default 3 mm escape window, 300 s with 1.75 mm) both stalled in the fan-out of the camera BGAs and made 29 and 18 of 302 connections. In the nominal placement the six resistor arrays and the camera capacitors sit inside the escape window, two arrays on the side of each camera that faces the MCU, and the element order of `CAM_ARRAY_MAP` is not matched to the ball positions. The spec wants the arrays at the cameras, so the layout step has to find where (the README's advice: keep the BGA sides that face the rest of the circuit clear) and in which element order; nothing in the netlist fixes either. The router was not run again after the review changes.

## 9. Not done

- No datasheet was read. Outside the repository only ST's two open pin-data files (data, fetched from raw.githubusercontent.com/STMicroelectronics/STM32_open_pin_data, SHA-256 in `check_pinmap.py`) and three web searches were used, all on 2026-11-13 and all recorded as PROVISIONAL. What the search tool returned is an extract or a summary of a page, not the page:
  - BQ25101 pin table and TS behaviour: ti.com/document-viewer/BQ25101/datasheet/pin_configuration_and_functions, ti.com/document-viewer/BQ25100/datasheet/pin_configuration_and_functions and .../detailed_description (SLUSBV8C; the pin table came back garbled: only "C1 CHG / PRE-TERM, C2 VSS", "floating TS or pulling high: TTDM; pulling low disables the IC", "R_ISET 0.54 to 13.5 kohm" were readable); dtsheet.com/model/4116777 (third-party copy for the BQ25101H: "OUT A1, IN A2, TS B1, ISET B2, CHG C1, VSS C2", "75 nA battery leakage").
  - AN2606 pin list for the STM32U575: manualshive.com/ru/manual/st/stm32u575-series/1355565?page=21 (third-party copy: USART1 PA9 / PA10, USART2 PA2 / PA3, USART3 PC10 / PC11, I2C1 PB6 / PB7, I2C2 PB10 / PB11, I2C3 PC0 / PC1, SPI1 PA4-PA7, FDCAN1 PB8 / PB9); a community.st.com thread on AN2606 rev 70 that quotes "SPI1_MOSI ... push-pull, pull-down mode".
- No copper and no routed board: that is the layout step. "ERC" here means the toolchain's `checks.run_checks` (electrical rules, BOM fields, footprints, placement, decoupling) plus KiCad's netlist of the generated schematic compared with the model. KiCad's DRC ran on the board without tracks only (0 errors, 2 warnings `isolated_copper` for the two planes nothing reaches yet; every connection is still open and counted as unconnected).
- AN2606 could not be read; the bootloader part of the pin-map proof is PROVISIONAL.
- The JEITA thresholds of the BQ25101 were not read against the NTC curve (release gate of the spec).
- The review's doubts about data-sheet facts were NOT resolved, because no data sheet could be read: the charger's minimum input and what it does below it (4.1), ST's supply-sequencing rule (8.1), the UCPD dead-battery behaviour and the drive of the FT_c pads (3.6), the capacitance of the MLCCs under bias (4.7), the pin-1 edge of the LCD tail (section 6). Each is marked PROVISIONAL where it is used; where a cheap change made the netlist right for either answer (the LED line off PA15, 2.2 uF capacitors, 150 kohm for R31) it was made.

## 10. What changed after the two netlist reviews

| Review finding | What was done |
|---|---|
| LCD tail wired in the straight order although the repository's evidence says it is mirrored | J1 is wired mirrored (pad 1 = VSSA ... pad 10 = SCLK), derived from one PROVISIONAL fact, `LCD_TAIL_PIN1_EDGE`; rule row "lcd c" measures the chain on the placed footprint (section 6) |
| charger input below its 4.45 V minimum at the low end of a USB source | table 4.1 redone against 4.45 V (negative margin shown); spec-inherited, escalated (8.1); proposed board-test value |
| VDDUSB before VDD with a dead cell | not changed in the netlist (the rail table fixes U11); amendment proposed, release gate (8.1) |
| PA15 / PB15 are UCPD CC pads, PB5 / PB14 their control pads | GRAIN_CP1 moved from PA15 to PB0, CHG_STAT from PB0 to PA15; check_pinmap section I; firmware notes on UCPD_DBDIS and on VBUS sensing (3.6) |
| 1 uF 10 V 0402 loses half its value at 5 V | C22, C23, C26, C27 are 2.2 uF; effective values stated (4.7) |
| four seeded defects passed every checker | pin tables of 30 library-backed parts compared with the installed KiCad symbols (row "pin tables"); R31's direction and value tested; the LCD chain tested; 17 more seeded defects, all caught. The reviewer's 32 text mutations of the design file were applied again to the file as it is now: all 32 are caught |
| inputs without a level in reset and in the ROM | accepted and written down (3.7); no parts added |
| VBUS_SENSE is not a measure of VDDUSB | firmware note; the divider is now on the pad net, removal is seen in 22 ms (4.3) |
| J1 placed by its anchor, body 1.5 mm behind the model | cannot be met with this land pattern: open item with the numbers (5.1), rule row "PCB k2"; the "PCB k" row no longer claims it. Closed by E24 and the rev E YAML |
| firmware must change before it matches the map | notes 2 and 4 of section 7 and `pinmap.json`: the present charge stop does nothing; three EXTI lines move |
| R31 (1 Mohm) does not hold PA3 high in light | R31 is 150 kohm (4.10); the sleep-current test needs a dark underside |
| VBUS-sense divider on VBUS_D instead of VBUS | moved to the pad net as the rail table has it, 100 kohm : 100 kohm (4.3) |
| six bare-copper footprints flagged "not fitted" | kept, bounded by a rule row and reported as a workaround (5.2). Removed at rev E |
| little margin at the cell, the charger and two post feet | RT1 moved 2.5 mm from the charger, four parts nudged to 0.2 mm from the post-foot squares; U1 against the cell is a constraint for the layout and the mechanical owner (8.3, 8.4) |
| documentation slips | five results instead of pass / fail with a count line (section 2); "PCB k" corrected; the gen_pins sentence corrected (3.5); the YAML's component edge clearance is now a rule row ("PCB l") |

## 11. Amendments E24, E25 and E26 worked into the netlist (2026-11-17, layout step)

Sections 1 to 10 were written before these three decisions; where they still say "Schottky
D17", "MCP1700-3.3 (U11)" or "J1 on the YAML point", this section and the generated tables
(sections 2, 4.1) are the current state. The processor's pin map did NOT change: the two
differences in `pinmap.json` are the U1 rotation (0 degrees, a layout fact) and one word of
a firmware note.

| | Before | Now | Rule row |
|---|---|---|---|
| E24 | J1 anchor on the YAML point (0, -13.9), open item | anchor (0, -12.90): mouth -17.30, pads to -10.40; a departure from the rev D YAML, none from the rev E YAML (5.1) | PCB k, PCB k2 |
| E25 | D17 B0530WS-7-F, SOD-323, VBUS to VBUS_D | **U12** TI LM66100DCKR, SC-70-6: VIN = VBUS (pad side), VOUT = VBUS_D, CE = VBUS_D, GND, ST open, pad 4 open. The reference D17 is retired (D1 to D16 are the LEDs; an IC is not a "D") | rail VBUS a, b, c |
| E26 | U11 MCP1700T-3302E/TT, SOT-23 | **U11** TI LP5907MFX-3.3/NOPB, SOT-23-5, pin table of U8; IN = VBUS_D, OUT = VDDUSB, **EN = V2V8**, pad 4 open | rail VDDUSB, pin tables |

PROVISIONAL, each from memory and none read from a data sheet:

- **`LM66100_PINS`** (one marked table in the design file): VIN 1, GND 2, CE 3, N/C 4, ST 5,
  VOUT 6. The KiCad library has no symbol for the part, so the rule checker has no second
  source: it only proves that the netlist follows the table.
- That the LM66100 conducts while CE is below VIN and opens when CE (= VOUT) rises above
  VIN; its behaviour when VBUS appears with VBUS_D at 0 V; on-resistance; that ST may float.
- **U11's enable pin loads the always-on rail.** As remembered, the LP5907's EN pin has an
  internal pull-down of about 1 Mohm (2.8 uA at 2.8 V). That current flows whenever V2V8 is
  up, in the cradle or not, and counts against the 25 uA sleep limit of E14 (firmware model
  20.6 uA, so about 23.4 uA; section 4.12 does not include it). If the data sheet confirms
  the pull-down and the margin is wanted back, a series FET or a regulator without the
  pull-down is the remedy; the spec owner decides. The enable threshold (1.2 V high as
  remembered) is met by 2.8 V.
- With U11 off out of the cradle its output is discharged by the regulator (LP5907 has an
  output discharge, as remembered); VDDUSB is then 0 V, as before.
- E26's purpose - VDDUSB never before VDD - holds as long as V2V8 comes from the cell; with
  an empty cell in the cradle V2V8 rises only when the charger has lifted VBAT, and VDDUSB
  follows it.
- LP5907 maximum input 5.5 V (memory) against a USB source of up to 5.5 V: no margin.

Also changed with this pass: `check_pinmap.py` section F. `firmware/hal/stm32u5/gl_pins.h`
is no longer the firmware's proposal but a file GENERATED from `pinmap.json` (it states the
SHA-256 of its source), so "the difference to gl_pins.h is exactly the CHANGED rows" could
no longer be evaluated (the old row pattern matched nothing and the check failed). Section F
now proves that every row of the header has the pin, pad and source of the pin map and
that the history ("was", "reason") is complete. `pinmap.json` has been exported again, so
its SHA-256 no longer equals the one the header states: **the firmware side must run
`make pins`** (no pin moves by it).

## 12. Revision E (E-EVT1, 2026-11-18)

The package moved from D-EVT1 to E-EVT1 with `design/master_params.yaml`. No part moved, no
net changed, no MCU pin changed (`pinmap.json` is byte-identical: SHA-256 d33ff53f...72e4;
its header line still reads "DESIGN_SPEC rev D with amendments E1 to E34" because the file's
content had to stay as the firmware's generated header hashes it).

| Amendment | What changed in this package |
|---|---|
| E24 (J1) | read from the YAML (`anchor`, `mouth_y`, `body_y`, `pads_end_y`, body box) instead of typed; rule row "PCB k2" is a pass, not a departure; the keep-out notch is `battery.board_keepout_notch`; the LCD-tail height limit is the new zone y -21.1 to -17.3; the build's exit status 2 is gone (5.1) |
| E25, E26, E27, E28 | already in the netlist (section 11). U12 now carries the Digi-Key code 296-53541-1-ND (docs/SOURCING.md A7); U11 deliberately carries none (A8 asks for the live US page first) |
| E35 (fine class) | the 0.100 / 0.100 mm class on F.Cu, In2.Cu and B.Cu inside two areas 5 mm beyond each camera ball field is as specified: `FINE_AREA_MARGIN`, track, clearance and the three layers are read from `pcb.net_classes.fine`; rule row "PCB c" tests them and requires one fab note that names E7 / E35, 0.100 mm and all three layers. The fab README and the quote request therefore name F.Cu, In2.Cu and B.Cu. Still a release gate (E7 as widened by E35): the fabricator's written acceptance. The CamPower class (0.15 / 0.10) remains a recorded departure |
| E36 | cradle board 1.0 mm (`../gl1_cradle/CRADLE_NOTES.md`) |
| workaround flag | `BARE_BOTTOM_COPPER_NOT_FITTED` removed (5.2) |

**The routing.** The stored routing's fingerprint covers the whole design dictionary (revision
string, fab notes, every part's status note), so it could not match after the revision stamp
changed, although nothing the router reads had changed. The board was therefore routed again
from nothing (the router is deterministic) and the result compared with the rev D routing:
see `LAYOUT_LOG.md`, section "Revision E".

**BOM status columns.** `<name>-bom-status.csv` now has "Status" (VERIFIED / PROVISIONAL: the
sourcing status of the exact part number, copied from the row of `docs/sourcing.csv` with the
same MPN; a part number without a row is PROVISIONAL), "Design evidence" (RESEARCH /
PROVISIONAL, the level of the pin table, land pattern and values) and "Design evidence note",
then the sourcing risk, the alternates named by the sourcing report (candidates, not approved) and the sourcing row (found by the line's references since the final audit). VERIFIED means "listed
for sale, seen on that date"; it is neither a stock promise nor a statement about the land
pattern. A line can be ordered only when both columns allow it.

**`docs/SOURCING.md` section 12, design actions, as they stand in the design files.**

| Action | State | Where / why |
|---|---|---|
| A1 1 uF: GRM155R61A105KE15D -> Samsung CL05A105KP5NNNC | applied | `CAPS["1u"]`, BOM item 3 (same 0402 footprint, value, voltage, dielectric) |
| A2 2.2 uF: GRM155R61A225KE95D -> Murata GRM155R61A225KE01D, second source Samsung CL05A225KP5NSNC | applied | `CAPS["2u2"]`, BOM item 6; the second source is in the alternates column. That KE01D succeeds KE95D is the report's inference: PROVISIONAL |
| A3 DC-bias curves of the 1 uF, 2.2 uF and 4.7 uF parts against what U7, U8, U11 and U9 need | needs an owner | no curve could be read here (no network); every effective value in 4.7 stays PROVISIONAL; a larger case size would be a footprint change |
| A4 alternate CL05B104KO5NNNC for the 100 nF line on both BOMs | applied | alternates column of both status BOMs; the Murata status question is on the line's risk column |
| A5 cradle fuse -> Littelfuse 0603L035YR, second source Bourns MF-FSMF035X-2 | applied | cradle `PTC`; trip 0.75 A against E6's "about 0.5 A" is a recorded departure for the spec owner; the 1206 fallback would be a footprint change (not made) |
| A6 Mill-Max 0914: tail 0.635 mm, hole from the 0.737 mm minimum; tail length | applied / closed by E36 | hole 0.80 mm finished, pad 1.60 mm; board 1.0 mm so that the 1.34 mm tail comes through (PROVISIONAL until the drawing is read) |
| A7 LM66100DCKR in place of D17, order code | applied | U12 (section 11), Digi-Key 296-53541-1-ND; pin table PROVISIONAL (data sheet not read) |
| A8 LP5907MFX-3.3/NOPB in place of the MCP1700-3302 | applied; order code open | U11; only the reel code 296-38557-2-ND was seen, on regional pages: the BOM says "order by MPN" until the live US page is read |
| A9 keep SFH 4053B, alternative Inolux IN-S42CTQIR | applied; data sheet open | BOM item 9 names the alternative; wavelength, package and polarity mark not read: the LED land pattern stays PROVISIONAL |
| A10 OVM7692-RYAA single source | not a design-file change | the risk is on BOM item 27; life-cycle statement and quotes are purchasing work |
| A11, A12 display and cell on a purchasing list above the board BOMs | partly applied; needs an owner | neither is a board part. The main assembly README now names both under "OFF-BOARD ITEMS"; the purchasing list itself has no file and no owner in this package. The display thickness (0.741 against 0.746 mm) is a YAML question |
| A13 U4 from Newark 62AK1744 at 5.75 | applied | BOM item 28 |
| A14 flash: tray or reel code | needs an owner | to be decided with the assembler; the BOM carries the tray code MX25R6435FZNIL0 and shows the reel code as alternate |
| A15 J1: FH12A on the FH12 land pattern, height 2.0 mm | open (PROVISIONAL gate) | the MPN keeps the A and the (55); the Hirose drawing has not been read; a different land pattern would be a footprint change. The E24 fallback connector has not been sourced |
| A16 STM32U585RIT6 price / lead; not the RIT6Q | not a design-file change | the BOM names STM32U585RIT6 |
| A17 order codes and prices | applied | U9 296-39933-1-ND, U7 MCP1700T-2802E/TTCT-ND, RT1 / RT2 490-18149-1-ND, R23-R27 311-68.0LRCT-ND, 100 nF 490-3261-1-ND (main, and now the cradle's C1), cradle R1 / R2 311-5.10KLRCT-ND (now entered); Y1 0.99, U4 5.75; D17 is gone |
| A18 alternates column for the passives (candidates; none is approved) | applied as a candidates column | the status BOM copies the alternates from `docs/sourcing.csv` by the references of each line, with their own VERIFIED / PROVISIONAL words; nothing is listed that the report does not list |
| A19 to A35 (balls, screws, feet, vent, films, tapes, foam, glass, adhesives) | not applicable here | mechanical parts and consumables; A20 (cradle screw) was answered by the mechanical package (M2 x 4) |
| 12.2 item 3 (`US_4L_FINE` of the toolchain is 0.09 / 0.09 mm) | not applicable to the boards | neither board uses that rule set: the main board's is `GL1_4L_0.10mm` (minimum 0.100 / 0.100 mm). The toolchain README still describes the 0.09 mm set as an option |
