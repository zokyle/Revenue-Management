/*
 * gl_provisional.h - every PROVISIONAL hardware fact the firmware depends on.
 *
 * DESIGN_SPEC.md (rev D with amendments E1 to E34: the "rev E" board) marks
 * facts as VERIFIED or PROVISIONAL.  Anything
 * provisional that changes what the firmware does is a named constant HERE
 * and nowhere else, with the reason and what to check.  When a release gate
 * is closed, change the value (if needed), move the constant to its module
 * and delete it from this file.
 *
 * Also collected here: numbers that are engineering ESTIMATES rather than
 * measurements (seating error, grain thresholds, flagstick prior), because a
 * reader must not mistake them for calibrated facts.
 */
#ifndef GL_PROVISIONAL_H
#define GL_PROVISIONAL_H

/* ======================================================================= */
/* OVM7692 camera cube                                                      */
/* ======================================================================= */

/** Register 0x0C bits 2 (data pins D[7:0]) and 1 (VSYNC/HREF/PCLK): output
 *  drive enables used to tri-state the idle camera on the shared bus.
 *  Register address and reset value 0x16 are VERIFIED (public Analog Devices
 *  msdk driver).  The bit MEANING comes from the OV7690 (sister sensor)
 *  datasheet and the POLARITY is inferred from the reset value having both
 *  bits set.  1 = "bit set means the pins are DRIVEN".
 *  Check: measure on the first board that the idle camera releases the bus;
 *  the firmware always sets or clears both bits together. */
#define GL_PROV_OV7692_REG0C_BIT_SET_MEANS_DRIVEN 1

/** PWDN pin polarity.  Active high with internal pull-down on the OV7690;
 *  not confirmed for the OVM7692.  1 = "PWDN high powers the sensor down". */
#define GL_PROV_OV7692_PWDN_ACTIVE_HIGH 1

/** Whether the sensor's outputs are high-impedance while PWDN is asserted is
 *  NOT confirmed.  0 = "assume they are NOT": a sensor in power-down keeps
 *  driving its pads (static levels) as long as register 0x0C enables them.
 *
 *  What that means, honestly: once both sensors have been configured the
 *  driver never relies on PWDN to free the shared bus (bus ownership is
 *  changed with register 0x0C only, break before make).  But POWER-UP cannot
 *  avoid it: both sensors leave their power-on reset with 0x0C = 0x16 (pads
 *  enabled) and can only be told otherwise over SCCB, one after the other,
 *  after PWDN release and the clock settle time.  If PWDN does not tri-state
 *  the pads, both sensors have their pads enabled for about 12 ms per rail
 *  cycle, of which about 6 ms with one of them streaming against the
 *  other's static levels (figures measured by the camera model, which
 *  follows this constant; tests/test_drv_cam.c asserts them as the accepted
 *  overlap).  THIS WINDOW CANNOT BE CLOSED IN FIRMWARE.  Release gate: read
 *  the PWDN pad state in the OmniVision datasheet.  If PWDN does not
 *  tri-state: PWDN pull-ups to V2V8_CAM with open-drain MCU pins (sensors
 *  start in power-down and no MCU pin ever drives high), or series
 *  resistors / a bus switch per camera.
 *  1 = "PWDN tri-states the pads": the model then counts no overlap. */
#define GL_PROV_OV7692_PWDN_TRISTATES_OUTPUTS 0

/** Register 0x0C bits this firmware does NOT own are written with their
 *  reset values: the reset value is 0x16 and the public Analog Devices
 *  driver (the only configuration known to run on hardware) writes 0xD6,
 *  i.e. it keeps bit 4 (YU/YV swap) SET.  The firmware owns bits 7 (flip),
 *  6 (mirror), 2 and 1 (output drive); bits 5, 3 and 0 are 0 at reset. */
#define GL_PROV_OV7692_REG0C_KEEP_BITS 0x10u

/** Image orientation after the fold prism.  A right-angle prism used as a
 *  mirror reverses the image along one axis, and which package edge is
 *  parallel to the image rows is unconfirmed.  The driver programs the
 *  sensor's flip / mirror bits (register 0x0C bits 7 and 6, VERIFIED
 *  meanings) so that the delivered frame is upright: row 0 = up, column 0 =
 *  left as seen looking out of the visor.  These two constants say which
 *  bits that needs.  Check: first image from the first board. */
#define GL_PROV_CAM_SENSOR_VFLIP 1
#define GL_PROV_CAM_SENSOR_HMIRROR 0

/** XVCLK range 6-27 MHz was seen only in older product-brief revisions. */
#define GL_PROV_CAM_XVCLK_HZ 12000000u

/** Time to wait after the camera rail is enabled before touching PWDN/SCCB,
 *  and after XVCLK starts before the first register write.  From memory of
 *  OmniVision power-up diagrams of this family, not from the OVM7692
 *  datasheet. */
#define GL_PROV_CAM_RAIL_SETTLE_MS 5u
#define GL_PROV_CAM_CLOCK_SETTLE_MS 3u

/* ======================================================================= */
/* Sharp LS013B7DH03 display                                                */
/* ======================================================================= */

/** FPC pin order, pin 1..10 (PROVISIONAL in DESIGN_SPEC section 4; matched
 *  by a Sharp table extract and three public designs, but which end of the
 *  tail is pin 1 on OUR connector is unconfirmed: a wrong guess mirrors all
 *  ten pins).  Firmware consequence: none as long as the PCB nets carry
 *  these names; kept here so the pin table has one home. */
#define GL_PROV_LCD_FPC_PIN_SCLK 1
#define GL_PROV_LCD_FPC_PIN_SI 2
#define GL_PROV_LCD_FPC_PIN_SCS 3
#define GL_PROV_LCD_FPC_PIN_EXTCOMIN 4
#define GL_PROV_LCD_FPC_PIN_DISP 5
#define GL_PROV_LCD_FPC_PIN_VDDA 6
#define GL_PROV_LCD_FPC_PIN_VDD 7
#define GL_PROV_LCD_FPC_PIN_EXTMODE 8
#define GL_PROV_LCD_FPC_PIN_VSS 9
#define GL_PROV_LCD_FPC_PIN_VSSA 10

/** EXTCOMIN: 32768 / 547 = 59.905 Hz, the divider DESIGN_SPEC section 4
 *  states (546 would be 60.015 Hz, just outside the 1-60 Hz range).
 *  Sharp publishes two ranges (54-65 Hz and 1-60 Hz); which is current is
 *  unconfirmed, and 547 ticks is inside both with any crystal tolerance.
 *  The netlist's pin map carries the divider (extcomin_lse_ticks);
 *  tools/gen_pins.py exports it as GL_PINS_EXTCOMIN_LSE_TICKS and
 *  tests/test_pins.c fails if the two differ.
 *  Still unconfirmed: the order of DISP and EXTCOMIN at switch-on.  The
 *  driver starts EXTCOMIN before raising DISP; a reviewer remembers the
 *  Sharp sequence as DISP first.  Check against the datasheet. */
#define GL_PROV_LCD_EXTCOMIN_PERIOD_LSE_TICKS 547u

/** Whether the LPTIM1 PWM output pin keeps toggling in Stop 2 was not
 *  confirmed (RM0456 chapter 58).  If 0, the app must stay in Stop 1 or
 *  idle sleep while the display is on. */
#define GL_PROV_LPTIM_PWM_RUNS_IN_STOP2 1

/** Display orientation in the puck: which way image row 0 faces.  The FPC
 *  tail exits at the rear (-y) edge; whether row 0 (first line address) is
 *  at the front or the rear, and whether columns run left-to-right, depends
 *  on the unconfirmed tail geometry.  The gfx layer draws in "screen"
 *  coordinates (x right = marker +x, y down = marker -y); these constants
 *  tell the LCD driver how to map screen rows/columns to line addresses and
 *  bit positions. */
#define GL_PROV_LCD_ROW0_AT_FRONT 1
#define GL_PROV_LCD_COL0_AT_LEFT 1

/** Offset of the active-area centre from the puck centre along y, in mm.
 *  master_params.yaml places the active area at the puck centre (0, 0) with
 *  the glass shifted 1.65 mm to the rear; that 1.65 mm is PROVISIONAL.  The
 *  UI assumes the aperture is centred on the active area. */
#define GL_PROV_LCD_ACTIVE_CENTRE_Y_MM 0.0f

/** SPI clock ceiling.  1.1 MHz comes from one open-source driver. */
#define GL_PROV_LCD_SPI_MAX_HZ 1000000u

/** Supply range 2.7-3.3 V is marked PROVISIONAL in DESIGN_SPEC (the BOM
 *  verification later saw it in a Sharp table extract).  The always-on rail
 *  is 2.8 V: only 100 mV of margin. */
#define GL_PROV_LCD_VDD_MIN_MV 2700u

/* ======================================================================= */
/* MCU / USB                                                                */
/* ======================================================================= */

/** Crystal-less USB (HSI48 with clock recovery) is PROVISIONAL. */
#define GL_PROV_USB_CRYSTALLESS_HSI48_CRS 1

/* ======================================================================= */
/* Power                                                                    */
/* ======================================================================= */

/** LiPo thresholds at rest, millivolts.  Engineering defaults for a 43 mAh
 *  cell under a ~1 mA average load; the cell datasheet has not been
 *  obtained.  LOW shows the battery warning, CRITICAL refuses camera reads
 *  (the camera rail draws ~90 mA from a very small cell). */
#define GL_PROV_BATT_LOW_MV 3500u
#define GL_PROV_BATT_CRITICAL_MV 3350u
#define GL_PROV_BATT_FULL_MV 4150u
#define GL_PROV_BATT_EMPTY_MV 3300u

/* ======================================================================= */
/* Estimates that are not measurements                                      */
/* ======================================================================= */

/** Seating error of the puck on turf, 1-sigma per axis, rad.  DESIGN_SPEC:
 *  "2-5 mrad per placement (estimate, unmeasured)".  The Python reference
 *  uses 2.5 mrad.  Used only for the confidence figure. */
#define GL_PROV_SEATING_SIGMA_RAD 0.0025f

/** Flagstick prior: 2.13 m (7 ft) total, 0.17 m of it in the cup, 7 %
 *  1-sigma.  UNVERIFIED in docs/research/grazing-vision.md. */
#define GL_PROV_STICK_TOTAL_HEIGHT_M 2.13f
#define GL_PROV_STICK_IN_CUP_M 0.17f
#define GL_PROV_STICK_HEIGHT_REL_SIGMA 0.07f

/** Flagstick diameter range, metres (UNVERIFIED).  Used to bound the
 *  plausible image width of a stick at a given range. */
#define GL_PROV_STICK_DIA_MIN_M 0.0127f
#define GL_PROV_STICK_DIA_MAX_M 0.0190f

/** Stereo calibration error left in a disparity after the factory
 *  calibration, px one-sigma (UNMEASURED: the calibration fixture does not
 *  exist yet).  It is the same in every strip and every read of a unit and
 *  is added to the disparity uncertainty of each read; it is what limits
 *  the stereo range beyond a few metres (0.05 px = 2.3 % at 6 m, 3.8 % at
 *  10 m with the 20 mm baseline). */
#define GL_PROV_STEREO_CAL_SIGMA_PX 0.05f

/** Lens blur (rms radius of the point-spread function, px) is only known
 *  to lie in this range until the lens is measured at EVT.  The width of a
 *  line (flagstick or not) is inferred from its profile minus the blur. */
#define GL_PROV_LENS_BLUR_SIGMA_MIN_PX 0.45f
#define GL_PROV_LENS_BLUR_SIGMA_MAX_PX 0.80f

/** Grain: DEFAULT modulation acceptance threshold stored in a fresh grain
 *  calibration record.  grain-sensing.md: "do not use a fixed 0.10 ... set
 *  it from the measured no-grain noise floor (gate 0); expect 0.25-0.3".
 *  This is only the value a unit has BEFORE gate 0 has been run; the code
 *  always reads the threshold from the calibration record. */
#define GL_PROV_GRAIN_MOD_THRESHOLD_DEFAULT 0.30f

/** Grain: cap on the total grain correction, as an equivalent slope
 *  (rise/run).  grain-sensing.md section 2.2. */
#define GL_PROV_GRAIN_MAX_EQUIV_SLOPE 0.008f

/** Grain: sign relating the photometric first-harmonic azimuth to the
 *  direction the grain pushes the ball.  +1 = the brightest illumination
 *  azimuth IS the push direction.  Unproven (validation gates 2-4). */
#define GL_PROV_GRAIN_HARMONIC_SIGN (+1.0f)

/** Grain prior strengths kappa (dimensionless, push = kappa * a_r) by
 *  grass type.  Golf lore, UNVERIFIED. */
#define GL_PROV_GRAIN_KAPPA_BENT 0.01f
#define GL_PROV_GRAIN_KAPPA_POA 0.02f
#define GL_PROV_GRAIN_KAPPA_BERMUDA 0.06f

/* ======================================================================= */
/* Added with the drivers (drivers/, app/): provisional device facts        */
/* ======================================================================= */

/* ---- OVM7692: identification, format, timing ---------------------------- */

/** Product id expected in PIDH:PIDL (registers 0x0A, 0x0B: addresses
 *  VERIFIED from the public Analog Devices driver; the VALUE 0x7692 is from
 *  memory of the OV7690 family and is not printed in that driver).  The
 *  driver refuses a camera that answers with another id only when
 *  GL_PROV_OV7692_ENFORCE_PID is 1. */
#define GL_PROV_OV7692_PID 0x7692u
#define GL_PROV_OV7692_ENFORCE_PID 1

/** Byte order of the YUV422 stream with register 0x0C bit 4 (YU/YV swap) at
 *  its RESET value (set: GL_PROV_OV7692_REG0C_KEEP_BITS), which is the only
 *  state known to run on hardware.  1 = the FIRST byte of every pair is
 *  luminance, so the DCMI byte-select keeps the even bytes.  This is a
 *  GUESS: the name "YU/YV swap" suggests that the bit exchanges U and V and
 *  leaves Y where it is, but no datasheet was available, and the camera
 *  model of the simulator encodes the same guess (it can prove nothing).
 *  Symptom if wrong: flat, low-contrast strips (chroma); fix: set to 0. */
#define GL_PROV_OV7692_Y_IS_FIRST_BYTE 1

/** Sync polarities and the pixel-clock edge on which data are valid, at
 *  the sensor's reset settings.  Not confirmed for the OVM7692. */
#define GL_PROV_OV7692_VSYNC_ACTIVE_HIGH 1
#define GL_PROV_OV7692_HREF_ACTIVE_HIGH 1
#define GL_PROV_OV7692_PCLK_RISING 1

/** Frame period with XVCLK = 12 MHz and the clock-tree registers left at
 *  their reset values.  UNKNOWN: the driver does not write PLL / divider
 *  registers because no verified values for 12 MHz exist in this project
 *  (the Analog Devices table is for another clock and a 64 x 64 image).
 *  34 ms assumes 30 frames/s.  Only time-outs and settle delays use it. */
#define GL_PROV_CAM_FRAME_PERIOD_MS 34u

/** Frames to let pass after a camera starts streaming (reset or wake from
 *  sleep) before a strip is trusted: exposure / gain loop settling.  Guess. */
#define GL_PROV_CAM_SETTLE_FRAMES 2u

/** SCCB calls the 9th bit of every byte "don't care".  OmniVision sensors
 *  of this family pull it low like an I2C acknowledge; that is from
 *  experience with sister parts, not from the OVM7692 datasheet.  1 = the
 *  STM32 backend's bit-banged SCCB reports GL_ERR_IO when the 9th bit stays
 *  high (missing or unpowered sensor); 0 = it ignores the bit. */
#define GL_PROV_OV7692_SCCB_ACKS 1

/** Time for the software reset (register 0x12 bit 7) to complete; the
 *  driver polls the bit and gives up after this. */
#define GL_PROV_OV7692_RESET_TIMEOUT_MS 50u

/**
 * Where the strip window is applied.
 *   1 = SENSOR-SIDE: the window is programmed into the sensor (HSTART 0x17,
 *       HSIZE 0x18, VSTART 0x19, VSIZE 0x1A, input size 0xC8..0xCB, output
 *       size 0xCC..0xCF; addresses VERIFIED from the Analog Devices driver)
 *       and the DCMI stores the whole, already windowed, frame.
 *   0 = MCU-SIDE: the sensor streams full VGA and the DCMI crop feature
 *       cuts the strip out (uses no unverified sensor register).
 * Both paths are implemented and tested on the host.  The MEANING of the
 * four start / size registers below is inferred from the OV7690 reset
 * values (HSTART 0x69, HSIZE 0xA4 = 656 / 4, VSTART 0x0C, VSIZE 0xF6 =
 * 492 / 2) and is NOT confirmed: if the first images are mis-framed, set
 * this to 0 and the device works unchanged.
 */
#define GL_PROV_OV7692_SENSOR_WINDOWING 1
#define GL_PROV_OV7692_HSTART_FULL 0x69u  /* register value for column 0 */
#define GL_PROV_OV7692_VSTART_FULL 0x0Cu  /* register value for row 0 */
#define GL_PROV_OV7692_H_UNIT_PX 4u       /* pixels per LSB of HSTART / HSIZE */
#define GL_PROV_OV7692_V_UNIT_LINES 2u    /* lines per LSB of VSTART / VSIZE */
#define GL_PROV_OV7692_H_BORDER_PX 16u    /* HSIZE covers the window plus this */
#define GL_PROV_OV7692_V_BORDER_LINES 12u /* VSIZE covers the window plus this */

/** During the L R R L sequence the idle camera is tri-stated (register
 *  0x0C) but NOT put to sleep, because the number of frames a sensor needs
 *  after waking is unknown and would be paid on every switch.  Sleep
 *  (register 0x0E bit 3) is used for a camera that idles longer than that.
 *  1 = sleep the idle camera on every switch as DESIGN_SPEC literally says
 *  (then every switch waits GL_PROV_CAM_SETTLE_FRAMES frames). */
#define GL_PROV_CAM_SLEEP_IDLE_ON_EVERY_SWITCH 0

/* ---- LS013B7DH03: serial timing ------------------------------------------ */

/** Chip-select set-up, hold and minimum low time in microseconds.  Sharp
 *  figures as remembered are 6, 2 and 2 us; the driver uses these rounded-up
 *  values.  Check against the current specification. */
#define GL_PROV_LCD_SCS_SETUP_US 10u
#define GL_PROV_LCD_SCS_HOLD_US 5u
#define GL_PROV_LCD_SCS_LOW_US 5u

/* ---- LSM6DSV16X: mounting ------------------------------------------------- */

/* How the sensor axes map onto the marker axes is NOT a constant of this
 * file any more: the netlist's pin map states it (imu_mounting) and
 * tools/gen_pins.py writes it into hal/stm32u5/gl_pins.h as
 * GL_PINS_IMU_MARKER_{X,Y,Z}_{AXIS,SIGN} (marker = sign * sensor axis;
 * index 0 = sensor X, 1 = Y, 2 = Z).  The identity placeholder that stood
 * here exchanged the two in-plane tilt axes on the rev E board and inverted
 * one.  The pin map's statement is itself PROVISIONAL (ST's axis drawing of
 * the LSM6DSV16X was not read). */

/** The temperature terms of the tilt calibration are applied only inside
 *  this window of IMU temperature; outside it the correction of the nearer
 *  end is used (a quadratic is not extrapolated without limit: a fit of
 *  three points over 16 K was 3 mg off at 0 and 45 C - phase-3 review,
 *  factory finding 7).  The window is the product's operating range with
 *  margin, NOT the range the unit's own fit covered: the record does not
 *  store that range (README open issues: a record version 3 would). */
#define GL_PROV_TILT_TEMPCO_T_MIN_C (-10.0f)
#define GL_PROV_TILT_TEMPCO_T_MAX_C 60.0f

/** Wake-on-motion threshold and the motion that ends a wait, in mg.
 *  Engineering guesses to be tuned on turf (pocket, cart vibration). */
#define GL_PROV_IMU_WAKE_THRESHOLD_MG 62u

/** Data-ready signalling on INT2.  0 = LATCHED: the line goes high with a
 *  new sample and stays high until the output registers are read (the
 *  part's reset behaviour as remembered: CTRL4 0x13 bit 1 DRDY_PULSED = 0).
 *  1 = pulsed (about 65 us per sample).  The driver writes CTRL4
 *  accordingly; the application works with either, because it also polls
 *  the line when no interrupt has arrived for two sample periods (a single
 *  lost edge would otherwise stop all samples in latched mode). */
#define GL_PROV_IMU_DRDY_PULSED 0

/** Absolute accuracy of the IMU's temperature sensor: NOT KNOWN here (the
 *  datasheet was not available; sister parts specify an offset of up to
 *  +-15 K, from memory).  The MCU's cell thermistor NTC2 is the firmware's
 *  temperature input and the two die sensors (IMU, MCU) are plausibility
 *  checks only: the NTC reading must lie within this many kelvin of AT LEAST
 *  ONE die sensor that is alive, or it is not believed and the firmware
 *  stops the charge.  (One, not both: a die sensor of unknown accuracy must
 *  not be able to veto a healthy NTC; an NTC that reads a fixed value
 *  disagrees with both.) */
#define GL_PROV_CHARGE_TEMP_MAX_DISAGREE_C 10.0f

/* ---- grain front end -------------------------------------------------------- */

/** Charlieplex wiring.  NO NETLIST EXISTS YET; this is a PROPOSAL for the
 *  schematic: LED pair k (k = 0..7, in the order of the azimuths) sits on
 *  the pin pair listed in drivers/grain_frontend.c, the RED LED conducts
 *  from the lower-numbered pin to the higher one and the NIR LED the other
 *  way (antiparallel).  With this rule every sneak path that exists while a
 *  red LED is lit contains at least one other red LED, so the low-voltage
 *  NIR LEDs cannot ghost.  1 = red conducts low pin -> high pin. */
#define GL_PROV_GRAIN_RED_ANODE_ON_LOW_PIN 1

/** Settling time after an LED is switched before the ADC samples (TIA
 *  470 kohm x 10 pF = 4.7 us, photodiode capacitance unknown), ADC samples
 *  averaged per reading and sampling time per sample.  Guesses. */
#define GL_PROV_GRAIN_SETTLE_US 500u
#define GL_PROV_GRAIN_ADC_AVG 16u
#define GL_PROV_GRAIN_ADC_SAMPLE_US 5u
/** Time for OPAMP1 and the mid-rail bias (2 x 100 kohm, 100 nF: 5 ms time
 *  constant) to settle after power-up.  Rev E: the bias divider is fed from
 *  the LCD_DISP line (it draws nothing asleep), so DISP must be HIGH, and
 *  must have been for 7 time constants = 35 ms (NETLIST_NOTES 4.10, firmware
 *  note 12; GL_PINS_GRAIN_BIAS_DISP_MS, which tests/test_pins.c compares
 *  with this).  gl_grain_fe_power() refuses with DISP low and waits this
 *  long, which covers the bias whenever DISP was switched on earlier. */
#define GL_PROV_GRAIN_POWER_SETTLE_MS 35u

/* ---- power -------------------------------------------------------------------- */

/** Battery divider ratio (2 x 1 Mohm, 1 % parts assumed): V_bat = ratio * V_pin. */
#define GL_PROV_BATT_DIVIDER_RATIO 2.0f

/* ---- charger: TI BQ25101 (E1) ---------------------------------------------------
 *
 * NO DATA SHEET WAS READ FOR THIS FIRMWARE.  What follows is what DESIGN_SPEC
 * section 4 and electrical/gl1_main/NETLIST_NOTES.md (4.2, 8.2) state - both
 * PROVISIONAL there, from web-search extracts of TI SLUSBV8 - completed from
 * memory of the BQ2510x family where the firmware or the simulator's charger
 * model needs a number.  drivers/power.c and hal/host/gl_sim_core.c use
 * these constants and nothing else, so a data-sheet reading changes one
 * place.  RELEASE GATE (DESIGN_SPEC section 7): the thresholds against the
 * NTC curve. */

/** Fast-charge current, microamperes: K / R_ISET = 135 A-ohm / 6.81 kohm (spec). */
#define GL_PROV_BQ25101_ICHG_UA 19820.0f
/** Termination: the charge ends when the current out of the charger falls
 *  below this fraction of the fast-charge current (spec: 10 %, fixed on the
 *  BQ25101).  THE CURRENT THAT COUNTS IS THE CHARGER'S OUTPUT CURRENT: the
 *  board hangs on the same node as the cell (no power path), so whatever the
 *  marker draws in the cradle is part of it - the reason for E32. */
#define GL_PROV_BQ25101_TERM_FRACTION 0.10f
/** Regulation voltage (BQ25101: 4.20 V) and the voltage the charger regulates
 *  to in its WARM zone (spec: 4.06 V), mV; the cell voltage below which a
 *  finished charge starts again (from memory of the family: about 100 mV
 *  under the regulation voltage). */
#define GL_PROV_BQ25101_VREG_MV 4200u
#define GL_PROV_BQ25101_VREG_WARM_MV 4060u
#define GL_PROV_BQ25101_RECHARGE_DROP_MV 100u
/** The charger's own temperature window, on ITS thermistor NTC1 (spec:
 *  JEITA profile; "halves the current when cold, lowers the charge voltage
 *  to 4.06 V when hot and does not charge outside its window").  Degrees C
 *  as the usual JEITA corners; the real thresholds are voltages on TS and
 *  depend on the fit of the part's bias current to this NTC: NOT READ. */
#define GL_PROV_BQ25101_T_COLD_C 0.0f   /* below: no charge */
#define GL_PROV_BQ25101_T_COOL_C 10.0f  /* below: half current */
#define GL_PROV_BQ25101_T_WARM_C 45.0f  /* above: 4.06 V */
#define GL_PROV_BQ25101_T_HOT_C 60.0f   /* above: no charge */
/** TS pulled to ground (what CHG_INHIBIT does through its MOSFET) disables
 *  the charger: 1 (extract: "pulling the pin low disables the IC"). */
#define GL_PROV_BQ25101_TS_LOW_DISABLES 1
/** TS OPEN (a cracked joint on NTC1) puts the charger into a test mode
 *  WITHOUT temperature monitoring, safety timer and termination (extract:
 *  "floating TS pin or pulling high puts part in TTDM"): 1.  The hardware
 *  window is then GONE, silently; the simulator models it, and the
 *  firmware's own gate on NTC2 is what is left while the firmware runs. */
#define GL_PROV_BQ25101_TS_OPEN_IS_TTDM 1
/** The charger's own safety timer, hours (from memory of the family: a fixed
 *  10 h fast-charge timer; NOT in the extracts).  0 = model none.  The
 *  firmware does not rely on it: its own limit is GL_PROV_CHARGE_MAX_MS. */
#define GL_PROV_BQ25101_SAFETY_TIMER_H 10u
/** CHG (open drain): LOW while a charge runs - pre-charge, fast charge,
 *  taper - and released when it has terminated, when the charger is disabled
 *  (TS low, temperature window, no input) or after a timer fault.  From
 *  memory of the family: NOT CONFIRMED whether a RE-charge after the first
 *  termination pulls CHG low again (1 = it does).  The other reading - CHG
 *  signals the FIRST charge cycle only, which is how this builder remembers
 *  the status pin of the BQ2510x / BQ2404x family being described - is a
 *  variant of the simulator's model (gl_sim_charger_stat_first_cycle_only;
 *  0 here makes it the default) and tests/test_e2e_power.c pins what the
 *  firmware does on it: a recharge shows as "full" although current flows,
 *  and the 6 h limit of E32, which counts the time CHG is low, does NOT see
 *  a recharge that an awake marker keeps from terminating (NOT MET for that
 *  variant; README open issue 39).  TO BE READ in TI SLUSBV8 before the
 *  status line is relied on for anything but the first cycle. */
#define GL_PROV_BQ25101_CHG_LOW_ON_RECHARGE 1
/** Minimum input voltage at which the charger works (docs/research/power.md,
 *  UNVERIFIED there).  The firmware cannot measure the charger's input; a
 *  charger that does not charge although it should shows as
 *  GL_CHGST_NOT_CHARGING (NETLIST_NOTES 4.1: with the Schottky the input is
 *  below this figure at the low end of a compliant source; E25 removes the
 *  Schottky). */
#define GL_PROV_BQ25101_VIN_MIN_MV 4450u

/* ---- the firmware's own charge supervision (NTC2) -------------------------------- */

/** The firmware stops the charge (CHG_INHIBIT high) outside these limits on
 *  ITS thermistor: DESIGN_SPEC section 4 gave the cell 0-45 C for charging,
 *  and that is NARROWER than the charger's own window, which goes on to
 *  60 C at 4.06 V.  With firmware running the charge therefore stops at
 *  45 C less the guard; without it (ROM loader, a hang, Shutdown) the
 *  charger's window alone decides.  Whether the cell may be charged in the
 *  charger's WARM zone is the cell data sheet's answer (release gate). */
#define GL_PROV_CHARGE_TEMP_MIN_C 0.0f
#define GL_PROV_CHARGE_TEMP_MAX_C 45.0f
/** ... measured with this much margin, because the firmware must stop
 *  before the TRUE temperature leaves the window: charging stops when the
 *  reading is below MIN + GUARD or above MAX - GUARD.  The divider's worst
 *  case is 1.09 K at 45 C and 0.90 K at 0 C (all eight corners of NTC 1 % at
 *  25 C, B 1 %, series resistor 1 %, with an ADC error of 0.2 % of full
 *  scale; computed again by tests/test_drv_power.c, which fails if it
 *  exceeds the guard), plus 0.11 to 0.16 K for the output resistance of the
 *  bias pin (NETLIST_NOTES 4.5).  1.5 K leaves about 0.3 K for what is NOT
 *  in that sum: the part's real R-T curve against the B equation, and a
 *  temperature difference between the cell and the NTC beside it
 *  (unmeasured: release gate). */
#define GL_PROV_CHARGE_TEMP_GUARD_C 1.5f
/** ... and resumes only this far inside the guarded window (hysteresis,
 *  our choice). */
#define GL_PROV_CHARGE_TEMP_HYST_C 2.0f
/** E32 backstop: after this much time in which the firmware has not held
 *  the charger stopped (VBUS present, CHG_INHIBIT released - whatever the
 *  charger's status output said in it: drivers/power.c) the firmware stops
 *  the charge.  6 h is the specification's figure.
 *  A full charge of the 43 mAh cell at 19.8 mA is about 2.2 h of constant
 *  current plus the taper; in the charger's COOL zone (half current) it is
 *  about 4.4 h plus the taper, so a charge from empty below 10 C may be cut
 *  a few percent short. */
#define GL_PROV_CHARGE_MAX_MS (6u * 3600u * 1000u)
/** After the backstop the charge may start again when the cell, having been
 *  seen at or above this voltage while the charge was stopped, has fallen
 *  below it (our choice: otherwise a marker left docked for weeks under a
 *  host that keeps it awake would run its cell down behind a charger that
 *  is held off).  A cell that never reached it in 6 h stays stopped until
 *  VBUS goes (drivers/power.c).
 *  OWNER DECISION (README open issues): since the backstop counts docked
 *  time whatever the status line says, it also holds the charger off on a
 *  marker that sleeps in its cradle with a finished charge; that marker then
 *  runs from its cell down to this voltage before the charge restarts.
 *  Measured on the model over 30 docked days (tests/test_e2e_power.c): the
 *  lowest state of charge is 79.3 % with 4000 mV here, and was 90.4 % in a
 *  scratch build with 4100 mV (the charger's own recharge threshold). */
#define GL_PROV_CHARGE_RESTART_MV 4000u
/** "Done": CHG released with the cell at or above this voltage.  Below it,
 *  with nothing the firmware knows of holding the charger, the charger is
 *  NOT CHARGING although it should (regulation voltage less the recharge
 *  drop, less 60 mV for the divider and the ADC). */
#define GL_PROV_CHARGE_DONE_MIN_MV 4040u

/* ---- E13: no camera read from a hot cell ----------------------------------------- */

/** No camera read is started when NTC2 READS above this (DESIGN_SPEC section
 *  6, E13; 60 C is the cell family's discharge limit, bom-verification-opto
 *  3.4, and a read draws about 96 mA).  The limit is applied to the READING,
 *  as the specification words it: the reading's error at 60 C is 1.43 K
 *  worst case (computed by tests/test_drv_power.c), so the true cell may be
 *  that much hotter when the gate still lets a read through. */
#define GL_PROV_READ_TEMP_MAX_C 60.0f
/** ... and reads are allowed again when it has fallen this far below the
 *  limit (our choice: 3 K, about twice the reading's error, so that a cell sitting
 *  at the limit does not flicker between the two answers). */
#define GL_PROV_READ_TEMP_HYST_C 3.0f

/* ---- cell thermistor of the MCU, NTC2 (E2) ---------------------------------------- */

/** Murata NCU15XH103F60RC (E2; it replaces the NCP15XH103F03RC): 10 kohm at
 *  25 C, B(25/50) = 3380 K NOMINAL, both taken as 1 % (PROVISIONAL: no data
 *  sheet, no R-T table).  Divider with 10.0 kohm 1 % (R19) from the GPIO
 *  NTC_BIAS to the ADC pin NTC_SENSE, the NTC (RT2) from there to ground.
 *
 *  EVERY R-T NUMBER IN THIS FIRMWARE IS DERIVED FROM THE B EQUATION
 *      R(T) = R25 * exp(B * (1 / T - 1 / 298.15 K)),   T in kelvin,
 *  with these two constants, and from nothing else: tests/test_drv_power.c
 *  computes its table from the same equation.  The part's real curve
 *  deviates from a one-B equation (typically a few tenths of a kelvin
 *  between 0 and 60 C for this class of part, more outside: NOT VERIFIED);
 *  replace the equation by the maker's table when it is in hand. */
#define GL_PROV_NTC_R25_OHM 10000.0f
#define GL_PROV_NTC_B_K 3380.0f
#define GL_PROV_NTC_SERIES_OHM 10000.0f
/** Time from NTC_BIAS high to the conversion.  The netlist puts no capacitor
 *  on the node (source resistance 2.3 to 7.4 kohm: it settles in
 *  microseconds, NETLIST_NOTES 4.5); 500 us is kept as margin for whatever
 *  the layout adds. */
#define GL_PROV_NTC_SETTLE_US 500u
/** ADC samples averaged and sampling time per sample (5 kohm source). */
#define GL_PROV_NTC_ADC_AVG 8u
#define GL_PROV_NTC_ADC_SAMPLE_US 20u
/** Open / short detection, as a fraction of full scale.  Above OPEN the NTC
 *  would be more than 49 times the series resistor (colder than -50 C, or
 *  broken off: the pin then sits at the bias level); below SHORT it would be
 *  under 2 % of it (hotter than 150 C, or shorted to ground, or NTC_BIAS not
 *  reaching the divider). */
#define GL_PROV_NTC_OPEN_FRACTION 0.98f
#define GL_PROV_NTC_SHORT_FRACTION 0.02f
/** With NTC_BIAS released the NTC pulls the sense pin to ground.  A reading
 *  above this fraction of full scale before the bias is switched on means
 *  the pin is held up by something else (a solder bridge to a rail): the
 *  measurement is not trusted. */
#define GL_PROV_NTC_IDLE_MAX_FRACTION 0.05f

/** Below this cell voltage, with no VBUS, the firmware stops everything it
 *  can (IMU powered down: no wake-on-motion; only the cradle wakes the
 *  device) so that the sleep drain does not take the cell down to its
 *  protection cut-off.  (The charger is on by default in hardware, so a
 *  cell at its cut-off CAN be recharged; storage mode still spares the cell
 *  the deep discharge.)  Engineering guess, no cell datasheet. */
#define GL_PROV_BATT_STORAGE_MV 3250u

/* ---- MX25R6435F: timing --------------------------------------------------------- */

/** Time-outs for page program and 4 kB sector erase, and the delays after
 *  entering / leaving deep power-down.  From memory of the Macronix
 *  datasheet (typical 3 ms / 60 ms, maxima 10 ms / 300 ms in the low-power
 *  mode; tDP and tRES about 30-35 us), with margin.  Verify. */
#define GL_PROV_MX25R_PROG_TIMEOUT_MS 100u
#define GL_PROV_MX25R_ERASE_TIMEOUT_MS 2000u
#define GL_PROV_MX25R_DP_DELAY_US 100u
#define GL_PROV_MX25R_SPI_HZ 8000000u

/* ======================================================================= */
/* MCU pin assignment                                                       */
/* ======================================================================= */

/* The pin map is the NETLIST's (electrical/gl1_main/pinmap.json, proven there
 * against ST's open pin data); hal/stm32u5/gl_pins.h is generated from it by
 * tools/gen_pins.py (`make pins`) and holds no pin of its own.  The layout
 * step may still exchange PROPOSED and CHANGED pins: then the header is
 * regenerated.  What stays PROVISIONAL about the pins is stated in the pin
 * map: the list of pins the ROM bootloader drives or listens on (memory of
 * AN2606), what the UCPD pads do, and the electrical limits of the pins.
 * The pin map is data of the STM32 backend only; nothing in core, drivers
 * or app depends on which pad a signal is on. */

/* ======================================================================= */
/* MCU low-power modes (rev E)                                               */
/* ======================================================================= */

/** Ship mode is the MCU's Shutdown mode, left through the wake-up pin of
 *  VBUS_SENSE.  From memory of RM0456 / DS13086, NOT READ: which of the four
 *  inputs of that wake-up line PC13 is (the selection field of PWR_WUCR3; the
 *  backend's identifier map names it), that a rising edge on it wakes the
 *  MCU from Shutdown, that the backup registers survive Shutdown, and that
 *  the pull-downs of PWR_PDCRx are applied in Shutdown when APC is set. */
#define GL_PROV_SHIP_MODE_IS_SHUTDOWN 1
/** In the cradle sleep of E32 the USB device may stay attached to a
 *  SUSPENDED bus and wake the MCU on resume.  Whether the STM32U585 can do
 *  that from Stop 2 is NOT KNOWN here (the sister families wake on USB from
 *  Stop 0 / 1 only): 0 = the backend uses Stop 1 while USB is in standby,
 *  which costs tens of microamperes more and is still far below the
 *  charger's termination current. */
#define GL_PROV_USB_WAKE_FROM_STOP2 0

#endif /* GL_PROVISIONAL_H */
