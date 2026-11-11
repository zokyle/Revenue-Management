/*
 * gl_provisional.h - every PROVISIONAL hardware fact the firmware depends on.
 *
 * DESIGN_SPEC.md (rev C) marks facts as VERIFIED or PROVISIONAL.  Anything
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

/** EXTCOMIN: 32768 / 547 = 59.905 Hz.  Sharp publishes two ranges (54-65 Hz
 *  and 1-60 Hz); which is current is unconfirmed.  547 ticks is inside both
 *  with any crystal tolerance.  (DESIGN_SPEC section 4 says 32768 / 546 and
 *  calls that 60 Hz; it is 60.015 Hz, ABOVE the 1-60 Hz range.  The spec
 *  sentence needs correcting; this file cannot do that.)
 *  Also unconfirmed: the order of DISP and EXTCOMIN at switch-on.  The
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

/** How the sensor axes map onto the marker axes (marker = sign * sensor
 *  axis).  The IMU's orientation on the PCB is not fixed by DESIGN_SPEC or
 *  master_params.yaml; identity is a placeholder for the layout to confirm.
 *  Axis index 0 = sensor X, 1 = Y, 2 = Z. */
#define GL_PROV_IMU_MARKER_X_AXIS 0
#define GL_PROV_IMU_MARKER_X_SIGN (+1)
#define GL_PROV_IMU_MARKER_Y_AXIS 1
#define GL_PROV_IMU_MARKER_Y_SIGN (+1)
#define GL_PROV_IMU_MARKER_Z_AXIS 2
#define GL_PROV_IMU_MARKER_Z_SIGN (+1)

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
 *  +-15 K, from memory).  The charge gate therefore never trusts it alone:
 *  the MCU's own die-temperature sensor must agree with it within this
 *  many kelvin, and BOTH must be inside the charging window.  A factory
 *  one-point offset is the proper fix if the datasheet confirms a large
 *  offset (release gate). */
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
 *  constant) to settle after power-up. */
#define GL_PROV_GRAIN_POWER_SETTLE_MS 25u

/* ---- power -------------------------------------------------------------------- */

/** Battery divider ratio (2 x 1 Mohm, 1 % parts assumed): V_bat = ratio * V_pin. */
#define GL_PROV_BATT_DIVIDER_RATIO 2.0f
/** Charging is allowed between these IMU temperatures (DESIGN_SPEC: 0-45 C)
 *  and re-enabled only this far inside the window (hysteresis, our choice). */
#define GL_PROV_CHARGE_TEMP_MIN_C 0.0f
#define GL_PROV_CHARGE_TEMP_MAX_C 45.0f
#define GL_PROV_CHARGE_TEMP_HYST_C 2.0f

/** Polarity of the charger's PROG enable pin (open-drain MCU output).
 *  1 = the rev C circuit: the PROG resistor goes to ground THROUGH the MCU
 *  pin, so LOW allows charging and a released pin stops it.
 *  CONSEQUENCE THAT NEEDS A HARDWARE DECISION: with this circuit the
 *  charger is OFF whenever the MCU is unpowered, so a cell that has reached
 *  its protection cut-off can never be recharged by the cradle (the MCU is
 *  fed from the cell).  The proposed fix is a PROG resistor to ground
 *  through an N-MOSFET whose gate is pulled up from VBUS, the MCU pulling
 *  the gate low to INHIBIT: charging then defaults to ON.  For that circuit
 *  set this to 0 (LOW = inhibit, released = charging allowed); nothing else
 *  in the firmware changes. */
#define GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE 1

/** Below this cell voltage, with no VBUS, the firmware stops everything it
 *  can (IMU powered down: no wake-on-motion; only the cradle wakes the
 *  device) so that the sleep drain does not take the cell down to its
 *  protection cut-off, from which the rev C charger circuit cannot recover
 *  it (see GL_PROV_CHG_PROG_LOW_ALLOWS_CHARGE).  Engineering guess, no
 *  cell datasheet. */
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

/* DESIGN_SPEC section 4 fixes 19 MCU pins (DCMI, MCO, SPI1 MISO, USB,
 * LPTIM1_CH1, OPAMP1).  The other 26 signals have NO assignment yet (no
 * netlist exists): hal/stm32u5/gl_pins.h carries this firmware's PROPOSED
 * assignment for them, each row marked GL_PINSRC_PROPOSED, generated and
 * cross-checked against the spec text by tools/gen_pins.py.  The pin map is
 * data of the STM32 backend only; nothing in core, drivers or app depends
 * on which pad a signal is on. */

#endif /* GL_PROVISIONAL_H */
