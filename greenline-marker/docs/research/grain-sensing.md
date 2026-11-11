# GreenLine research: sensing putting-green grain (blade lean direction) and its effect on the putt

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web, and neither could the report it was checking.

- Web search: four queries were attempted (OPT4001 datasheet, OPT4001DTSR at DigiKey, Vishay VLMS1500-GS08, OPT4003-Q1). All four were refused with "web search budget is used up" (a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.ti.com` (two pages), `www.vishay.com` and `www.digikey.com` all failed to resolve. The session's network is limited to an allowlist that contains no component-maker, distributor or reference hosts. No further hosts were tried, as the tool instructs.
- No workaround was attempted (no search engines through other tools, no proxies or archive services).

Consequences:

- **No part number, dimension, price, stock level or lifecycle status in this document was confirmed against a live source.** Every such item is marked UNVERIFIED. The first report took all of them from model memory, and said so. Where this reviewer's recollection agrees, that is noted, but it is the same kind of memory and is not independent confirmation.
- **No literature citation was confirmed.** The agronomy statements and the paper references (Brede 1991, Penner 2002, Sandmeier 1998, Gates 1965, and so on) are UNVERIFIED.
- What was checked here:
  1. Every formula and number in the first report that can be recomputed was recomputed with local scripts (`grain-sensing-checks/check_grain.py`).
  2. The seating-tilt analysis was redone from first principles and with a numerical ring-sensor simulation. One of the first report's design conclusions does not survive (section 4, finding 6).
  3. A Monte-Carlo model of discrete grass blades was added (`grain-sensing-checks/mc_blades.py`). It exposes a noise source the first report did not quantify (section 4, finding 7).
  4. Two reference datasets were available through the Python package index and were used as independent sources: the CIE 1924 photopic luminosity table (package `colour-science`) and the PROSPECT-D leaf optics model (package `prosail`). They confirm the first report's photopic weights and its leaf reflectance and transmittance figures.

Before any of the parts below go on a schematic, someone with network access must open the datasheets and live distributor pages. Hosts that need to be allowed: `www.ti.com`, `www.vishay.com`, `www.digikey.com`, `www.mouser.com`, `www.arrow.com`, `www.newark.com`, and the sites of ams OSRAM, Kingbright, Lumex, SparkFun and Adafruit. For the agronomy questions: `www.usga.org` and a literature search.

## 1. Summary

The question is whether a downward-looking ring of about eight LEDs and one photodetector in the base of the marker can read the direction the grass blades lean (grain), and whether that reading can improve the aim line.

What holds up:

- The putt model arithmetic is correct. With a grain strength k, rolling deceleration a0(1 - k cos(angle to down-grain)) gives a down-grain to into-grain Stimp ratio of (1+k)/(1-k). At Stimp 10, k = 0.05 is a 1.0 ft difference and is equivalent to a 0.39% slope. If grain also acts as a sideways force of the same size, a 3 m cross-grain putt that dies at the hole drifts k x D / 2 = 7.5 cm, and about 23-30% less at a firmer pace. All recomputed and confirmed.
- The optical principle is sound and the sign convention is right. A facet model and an independent numerical simulation both put the brightest LED on the up-grain side, so the down-grain direction is the bright azimuth plus 180 degrees.
- Red light near 630 nm is a reasonable choice. PROSPECT-D gives a green leaf about 5-6% reflectance and 87-94% absorption at 630 nm, against about 45% reflectance and 4-8% absorption at 850 nm, so red light scatters once and near-infrared scatters many times. The CIE table gives photopic weights of 0.265 at 630 nm and 0.061 at 660 nm, as the first report said.
- The first report's overall stance is right: grain sensing is the least certain function of the device, and it should be a low-weight, validation-gated correction with a no-hardware fallback.

What does not hold up, or was missing:

- **There is no tilt-immune LED geometry.** The first report derived that side-emitting LEDs at a height of r/sqrt(3), or LEDs aimed at 35 degrees elevation, cancel the false signal from a tilted seat. The derivation treats a tilt as a change in LED height at a fixed horizontal offset. For a rigid tilt about the sensed spot, the distance and emission angle do not change; only the incidence angle on the turf does. The false first harmonic is then about cot(elevation) per radian of tilt for any emitter pattern: 4.8% per degree at 20 degrees elevation, 3.0% at 30 degrees, 2.5% at 35 degrees. The simulation gives 1.9-3.5% per degree for the geometries the first report called immune. A tilted canopy is optically the same thing as blades whose mean surface normal is tilted by the same angle.
- **Blade-sampling noise is as large as the signal for a single reading.** The field of view holds only a few dozen leaf facets, and each LED lights mostly the turf closest to it (near-to-far irradiance ratio about 140:1 across the recommended 8 mm field of view, not the 7:1 quoted). In the Monte-Carlo model, turf with no grain at all gives a median first-harmonic modulation of 0.10-0.23. The first report's acceptance rule (modulation above 0.10) would therefore accept about half of the no-grain readings. With moderately aligned blades (mean resultant length 0.3-0.5) a single reading lands within 30 degrees of the true direction 33-76% of the time, before tilt, patchiness or dew are added.
- **The aim line depends on the least-supported number.** Down-grain against into-grain speed fixes only the along-track strength. The sideways drift (k x D / 2) follows only if grain acts as a force vector. If grain is purely a direction-dependent rolling resistance, the sideways force on a cross-grain putt is zero. Golf lore says putts drift with the grain, but no measurement was found by either pass.
- Smaller corrections: energy per read is 5-50 mJ, not about 2 mJ (still negligible); the near-infrared photocurrent is probably tens of times the red one, not 7 times; the photopic detector probably needs conversions of 12.7-25 ms or longer rather than 6.5 ms (from recollection of the OPT4001 datasheet, UNVERIFIED).

Bottom line: keep the sensor on the first engineering build as an experiment, because it costs a few dollars and little volume. Do not present its output as a measurement until it passes the gates in section 2. The default grain input should be the prior (fall line plus grass type chosen by the user). Reviewer's estimate that the optical reading measurably improves the aim line: 15-25%.

## 2. Final recommendation

"Verified" here means the reasoning and arithmetic were checked. Every part detail is UNVERIFIED.

### 2.1 Hardware for the first engineering build

- **Detector, red path: Texas Instruments OPT4001** digital light sensor at nadir, behind its own clear window and a black baffle. Reported packages: SOT-5X3 (2.1 x 1.9 x 0.6 mm, has an interrupt pin) and PicoStar (0.84 x 1.05 x 0.226 mm). UNVERIFIED.
- **Detector, dual-band path: a broadband silicon photodiode** (reported candidate Vishay VEMD8080, 4.8 x 2.5 x 0.48 mm) with a transimpedance stage into the MCU ADC, on a second footprint beside the OPT4001. The TI OPT4003-Q1 (visible plus near-infrared channels) is an alternative once its datasheet has been read. UNVERIFIED.
- **Emitters: 8 red chip LEDs, 0402 size, about 624-636 nm** (reported candidate Vishay VLMS1500-GS08, 1.0 x 0.5 x 0.35 mm; alternates Kingbright APHHS1005SURCK and Lumex SML-LX0402SIC-TR). UNVERIFIED.
- **Change from the first report: 8 near-infrared 0402 LEDs, not 4, each placed beside a red LED** (reported candidate ams OSRAM SFH 4053, 850 nm). Co-located pairs light the same patch of turf from the same direction, so the red to near-infrared ratio cancels more of the geometry and patch-to-patch variation. Sixteen LEDs need five charlieplex pins (five pins drive up to 20).
- **Recess: build two variants on the test boards.**
  - Variant A (first report's layout): LEDs on a 6 mm radius, 2.2 mm above the canopy plane, field of view 8 mm, recess about 13-14 mm across.
  - Variant B: LEDs on a 9 mm radius, field of view 10 mm, recess about 20 mm across. In simulation this cuts the median direction error by roughly a third (illumination is lower and more even) but returns about 4.6 times less light and is about 1.5 times more sensitive to tilt. Whether a 20 mm recess fits is a system packaging decision.
  - Matte black walls, a flat annular land around the recess, separate potted windows for every emitter and for the detector, as in the first report.
- **Side-emitting LEDs are optional.** They are no longer justified by tilt immunity. They may still be worth one test variant because they give lower, more even illumination (simulated modulation for blades leaning 80 degrees: 0.49, against 0.26 for variant A).
- No humidity sensor. No off-the-shelf downward imager in this build.

### 2.2 Firmware

- Per LED: dark, on, dark, with a fixed detector range; 3-4 interleaved cycles; reject the read if dark frames drift or the IMU sees motion. Unchanged.
- LED current 20 mA and detector conversions of 12.7-25 ms or longer, pending the datasheet check of OPT4001 resolution at short conversion times.
- White-reference gain calibration is mandatory, not optional. A photopic detector turns LED colour spread into gain spread: the CIE weight is 0.333 at 624 nm and 0.208 at 636 nm, a factor of 1.6 across a 12 nm bin.
- **Do not use a fixed 0.10 modulation threshold.** Set the acceptance threshold from the measured no-grain noise floor of the final geometry (gate 0 below). Expect it to be near 0.25-0.3 for a single reading.
- Keep a running vector average of the readings taken on the same green and weight it by the number of readings; a single reading is weak evidence.
- Keep two parameters, k_long (speed) and k_lat (sideways drift). The aim line uses k_lat. Until it has been measured, bound it between 0 and k_long and cap the total correction at an equivalent slope of 0.8%.
- Default behaviour: prior-based estimate (down the fall line, strength from the grass type the user selects), with the optical reading mixed in only when its modulation is well above the noise floor.

### 2.3 Validation gates

0. **Noise floor (new).** On turf with no deliberate lean and on brushed turf, take at least 50 readings at spots 2-3 cm apart inside one mowing stripe. This gives the false-modulation distribution and the spot-to-spot repeatability. The rotation test below cannot do this job, because local relief, patchiness and blade-sampling noise all rotate with the turf.
1. Bench: white-tile residual under 1%; tilted-tile response measured and compared with cot(elevation) per radian.
2. Rotation test on turf: the reading must rotate with the turf, not with the device. Necessary, not sufficient.
3. Stripe test: readings in adjacent mowing stripes compared with ball-roll anisotropy.
4. Ball-roll ground truth: the 8-direction short-ramp roll test with a precision level. **Record the sideways offset of every roll as well as the distance**, so that k_lat is measured and not assumed. The level must be accurate (not merely readable) to about 0.02 degrees: at Stimp 10 a slope error of 0.078% looks like k = 0.01.
5. Field and closed-loop gates as in the first report (several grass types and conditions; the correction must cut lateral miss on bermudagrass and must not worsen it on bentgrass).

If gates 0, 2 or 3 fail, ship the prior-based estimate only and keep the optical hardware for data collection.

### 2.4 Fallback

Prior-based grain estimate with no optical input: direction from the device's own fall-line measurement, strength from a user-selected grass type. It needs no extra hardware. Its assumptions (grain tends to run downhill, and so on) are golf lore and are UNVERIFIED.

## 3. Candidates

Every specification, dimension, price, stock and lifecycle entry in this table is **UNVERIFIED**. The values are the first report's, which came from model memory. "Agrees" in the last column means the reviewer's own recollection matches; it is not a confirmation. No price or stock figure could be checked on 2026-11-11.

| Name | MPN | Maker / HQ | Key specs (UNVERIFIED) | Dimensions mm (UNVERIFIED) | Interface / supply (UNVERIFIED) | Price USD (UNVERIFIED) | US distributors / stock | Lifecycle | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Fast digital light sensor | OPT4001DTSR (SOT-5X3-8), OPT4001YMNR (PicoStar-4) | Texas Instruments / USA | 12 conversion times 600 us to 800 ms; full scale about 83 klux (PicoStar) or 117 klux (SOT); about 0.3-0.44 mlux resolution at 800 ms; photopic response; about 30 uA active | SOT-5X3: 2.1 x 1.9 x 0.6; PicoStar: 0.84 x 1.05 x 0.226 | I2C; 1.6-3.65 V | about 0.6-1.5 at 1k | Expected at DigiKey, Mouser, Arrow, TI store; stock not checked | Believed active; not checked | Recommended (red path). Recollection agrees. |
| Dual-channel visible + NIR light sensor | OPT4003-Q1 (orderable suffix unknown; reviewer recalls OPT4003DNPRQ1, low confidence) | Texas Instruments / USA | Photopic channel plus NIR channel; conversion options similar to OPT4001 | About 2 x 2 x 0.65 | I2C; about 1.6-3.65 V | unknown | Expected at DigiKey, Mouser; not checked | unknown | Viable for the dual-band path; read the datasheet first. |
| Ambient light sensor | OPT3001DNPR | Texas Instruments / USA | 0.01 lux to 83 klux; conversion 100 or 800 ms only; about 1.8 uA | USON-6: 2.0 x 2.0 x 0.65 | I2C; 1.6-3.6 V | about 1-2 at 1k | Expected at DigiKey, Mouser, Arrow; not checked | Believed active; not checked | Fallback detector. Slow: 16 conversions take 1.6 s per cycle. Recollection agrees. |
| Ambient light sensors | VEML7700-TT, VEML6030 | Vishay / USA | 16-bit; integration 25-800 ms | VEML7700: 6.8 x 2.35 x 3.0; VEML6030: 2.0 x 2.0 x 0.85 | I2C; 2.5-3.6 V | about 1-2 | Expected at DigiKey, Mouser; Adafruit breakout for VEML7700; not checked | unknown | Rejected (VEML7700 too tall; both slower). Recollection agrees. |
| Light-to-digital converter | TSL25911FN | ams OSRAM / Austria and Germany | Two channels; integration 100-600 ms | about 2.0 x 2.4 x 0.7 | I2C; about 3.3 V | unknown | Expected at DigiKey, Mouser; not checked | unknown | Rejected (too slow for interleaved on/off). |
| Low-profile PIN photodiode | VEMD8080; smaller alternative VEMD1060X01 | Vishay / USA | VEMD8080: about 4.5 mm2 area, 350-1100 nm | VEMD8080: 4.8 x 2.5 x 0.48; VEMD1060X01: 2.0 x 1.25 x 0.85 | Analog; needs transimpedance stage and MCU ADC | about 0.5-1.5 | Expected at DigiKey, Mouser, Arrow; not checked | unknown | Fallback detector and the dual-band route. Recollection agrees. |
| Photopic chip photodiode | SFH 2716 family | ams OSRAM / Austria and Germany | Eye-like spectral response | about 2.0 x 1.25 x 0.8 | Analog | unknown | Expected at DigiKey, Mouser; not checked | unknown | Viable, low priority. No confident recollection. |
| Red 0402 chip LED | VLMS1500-GS08 | Vishay / USA | Super red, dominant about 630 nm; wide pattern; Vf about 2.0 V | 1.0 x 0.5 x 0.35 | GPIO and series resistor; 10-20 mA pulses | about 0.10-0.30 | Expected at DigiKey, Mouser, Arrow; not checked | unknown | Recommended emitter. Recollection agrees. Luminous intensity not known; it sets the signal level. |
| Red 0402 chip LED | APHHS1005SURCK | Kingbright / Taiwan (US arm in California) | Hyper red, dominant about 630 nm | 1.0 x 0.5 x about 0.5 | GPIO and series resistor | about 0.10-0.30 | Expected at DigiKey, Mouser; not checked | unknown | Fallback emitter. |
| Red 0402 chip LED | SML-LX0402SIC-TR | Lumex (ITW) / USA | Super red, about 636 nm peak | about 1.0 x 0.5 x 0.5 | GPIO and series resistor | unknown | Expected at DigiKey, Mouser; not checked | unknown | Fallback emitter. |
| Right-angle red chip LED | APA1606SURCK (suffix uncertain) | Kingbright / Taiwan | Emits parallel to the PCB | about 1.6 x 1.15 x 0.6 | GPIO and series resistor | unknown | Expected at DigiKey, Mouser; not checked | unknown | Optional test variant. The tilt-immunity argument for it is withdrawn (section 4, finding 6). |
| NIR 0402 chip LED | SFH 4053 (850 nm), SFH 4043 (about 940-950 nm) | ams OSRAM / Austria and Germany | Wide pattern; Vf about 1.5 V | 1.0 x 0.5 x 0.45 | GPIO and series resistor | about 0.3-0.6 | Expected at DigiKey, Mouser; not checked | unknown | Viable. Use 8, co-located with the red LEDs. Recollection agrees. |
| Near-field optical tracking sensor | PAA5100JE-Q | PixArt / Taiwan | Working range 15-35 mm; raw frame about 35 x 35 pixels | about 6 x 6, over 2 high | SPI | unknown | Not believed stocked at DigiKey or Mouser as a bare part | unknown | Rejected (focus range, height, sourcing). |
| Optical-flow sensor | PMW3901MB-TXQT | PixArt / Taiwan | Working range 80 mm to infinity | 6.0 x 6.0 x 2.28 | SPI | unknown | Breakout boards only, to the reviewer's knowledge | unknown | Rejected. |
| Miniature tracking chip | PAT9125EL | PixArt / Taiwan | No confirmed frame output | unknown | I2C or SPI | unknown | unknown | unknown | Rejected. |
| 1 x 1 mm camera module | NanEyeC | ams OSRAM / Austria and Germany | About 320 x 320; bit-serial output | 1.0 x 1.0, about 2.3-2.8 high | Proprietary serial | high | unknown | unknown, possibly not for new designs | Rejected. |
| Low-power image sensor used as a downward imager | HM01B0 family; SparkFun breakout SEN-15570 | Himax / Taiwan | 320 x 320 mono | bare sensor about 3 x 3 x under 1; lensed modules about 4 high | Parallel or serial video plus I2C | breakout about 10-15 | SparkFun historically; not checked | unknown | Bench instrument now; possible second-generation sensor with custom optics. |
| Humidity / temperature sensor | SHT40-AD1B-R2 | Sensirion / Switzerland | about +/-1.8 %RH | 1.5 x 1.5 x 0.5 | I2C; 1.08-3.6 V | about 1.5-2.5 | Expected at DigiKey, Mouser; not checked | unknown | Unpopulated footprint only. |
| Humidity / temperature sensor | HDC3020 / HDC3022 | Texas Instruments / USA | about +/-1.5 %RH; HDC3022 has a factory IP67 filter | 2.5 x 2.5 x 0.8 | I2C; 1.62-5.5 V | about 2-3 | Expected at DigiKey, Mouser; not checked | unknown | Not for this build. |
| Ground-truth method | n/a | in-house fixture | Short ramp rolled in 8 directions, 3 balls each; slope from a precision level; fit distance and sideways offset | n/a | n/a | n/a | n/a | n/a | Recommended, with two additions (section 2.3, gate 4). |
| Prior-based grain estimate | n/a | firmware | Direction from the fall line, strength from grass type | n/a | n/a | n/a | n/a | n/a | Fallback and default. |

## 4. Key findings

1. **Putt model arithmetic is correct.** Confidence: high (recomputed). With release speed 1.83 m/s, Stimp 8 / 10 / 12 ft give a0 = 0.687 / 0.549 / 0.458 m/s2. Down-grain to into-grain ratio (1+k)/(1-k). At Stimp 10: k = 0.02, 0.05, 0.10 give 0.40, 1.00, 2.02 ft difference and 0.157%, 0.392%, 0.784% equivalent slope. Equivalent slope equals k times the rolling resistance coefficient (0.0784 at Stimp 10). The release speed itself is UNVERIFIED; a rough energy calculation from recalled Stimpmeter geometry gives 1.91 m/s at the foot of the ramp, which is consistent with 1.83 m/s on the turf.

2. **Sideways drift of k x D / 2 is correct mathematics on an unproven assumption.** Confidence: high for the mathematics, low for the physics. Numerical integration of a constant sideways acceleration k x a0 on a 3 m putt gives 3.00, 7.48 and 14.9 cm for k = 0.02, 0.05, 0.10, against the closed form 3.0, 7.5, 15.0 cm. Rolling 0.30-0.43 m past the hole reduces the drift at the hole by 23-30% (the first report said 25-35%). If grain only changes rolling resistance with direction, the sideways force on a cross-grain putt is zero and so is the drift. The aim line depends on this term.

3. **The k values are priors, not data.** Confidence: low. Neither pass found a quantitative with-grain against against-grain study. The proposed ranges (bentgrass and Poa 0-0.02; groomed ultradwarf bermudagrass 0.02-0.05; grainy bermudagrass, paspalum, zoysia, kikuyu 0.05-0.12) are the first report's estimates. UNVERIFIED. For scale: the equivalent slope of grain under these priors (0.16-0.94%) is the same size as the marker's own seating uncertainty estimated in `inertial-sensors.md` (2-5 mrad, that is 0.2-0.5%).

4. **Sign convention and facet contrast are correct.** Confidence: medium (model-level; no turf data). For a blade leaning phi from vertical and an LED at elevation e, the upper face receives cos(phi - e) when lit from the up-grain side and max(0, -cos(phi + e)) from the down-grain side: 0.77 against 0 for 60 and 20 degrees; 0.50 against 0.17 for 80 and 20 degrees; 0.71 against 0.42 for 80 and 35 degrees. In general the first-harmonic modulation is cot(phi) x cot(e) until it clips. The simulation puts the bright azimuth exactly opposite the lean direction.

5. **Leaf optics support red for contrast and near-infrared as a reference.** Confidence: medium to high (PROSPECT-D run in this session; single-leaf values, not canopy). For three parameter sets spanning thin to thick green leaves:

   | Wavelength | Reflectance | Transmittance | Absorbed |
   |---|---|---|---|
   | 450 nm | 4.1% | 0.0-0.3% | about 96% |
   | 550 nm | 12.8-14.9% | 8-19% | 66-79% |
   | 630 nm | 5.0-5.9% | 1.6-7.1% | 87-94% |
   | 660 nm | 3.7-4.0% | 0.3-2.8% | 93-96% |
   | 850 nm | 43-49% | 43-53% | 4-8% |

   The first report's figures (5-8% in blue and red, 10-20% in green, 40-50% in near-infrared) are close; blue and 660 nm reflectance are nearer 4%. Photopic weights from the CIE 1924 table: 0.567 at 605 nm, 0.265 at 630 nm, 0.061 at 660 nm, matching the first report.

6. **Seating tilt and local relief: the size was about right, the proposed cure does not exist.** Confidence: high for the geometry (analytic result and simulation agree to 1%), medium for its relevance to real turf.
   - For a rigid tilt delta between the sensor and the canopy about the sensed spot, the false first harmonic at the centre of the field of view is (r / h) x delta, that is cot(e) per radian, for any emitter pattern.
   - Simulated values per degree of tilt, uniform Lambertian canopy: flat LEDs at r = 6 mm, h = 2.2 mm: 4.7% (1 mm field of view), 5.3% (4 mm), 6.7% (8 mm). Flat LEDs at r = 9 mm, 10 mm field of view: 9.7%. The first report's 7% figure for r = 6 mm is therefore the right size.
   - Geometries the first report called tilt-tolerant: LED aimed at the centre from 35 degrees: 1.9-2.4% per degree (its formula predicts 0.03%). Side emitter at h = r / sqrt(3): 2.2-2.9% (formula predicts 0). Side emitter at r = 4.5 mm, h = 2.2 mm: 3.5% (formula predicts 0.8%).
   - Lean contrast and tilt artifact both scale with cot(e), so in this model changing the LED elevation does not change their ratio. A 1 degree tilt looks like a 1 degree tilt of the mean blade surface normal. Blades leaning 80 degrees from vertical with a resultant length of 0.3 are worth roughly 3 degrees.
   - A relief of 0.1-0.2 mm across an 8 mm patch is 0.7-1.4 degrees. This is a property of the turf, so it passes a rotation test.

7. **Blade-sampling noise is the main limit on a single reading (new finding).** Confidence: medium for the order of magnitude, low for exact values (reviewer's Monte-Carlo model, no turf data; shoot density from memory).
   - Flat LEDs 2.2 mm above the turf light it very unevenly. Near-edge to far-edge irradiance ratio for one LED at r = 6 mm: 11:1 across a 4 mm field of view (the first report said 7:1, which is the figure for an isotropic source), 141:1 across 8 mm, 461:1 across 10 mm. Each LED therefore reads a crescent of turf next to itself, and the irradiance-weighted LED elevation is 31 degrees, not the 20 degrees at the centre. The fully aligned modulation for blades leaning 80 degrees falls from 0.48 (centre) to 0.26 (8 mm field of view).
   - Monte-Carlo, variant A (r = 6 mm, 8 mm field of view), 50-100 facets per cm2, two placement models, 30% non-directional background, single reading:

     | Blade alignment (resultant length R) | Median modulation | Median direction error | Within 30 degrees |
     |---|---|---|---|
     | 0 (no grain) | 0.10-0.23 (90th percentile 0.18-0.42) | random | n/a |
     | 0.3 | 0.14-0.25 | 29-51 degrees | 33-51% |
     | 0.5 | 0.21-0.27 | 16-38 degrees | 41-76% |
     | 0.8 | 0.31-0.37 | 9-24 degrees | 61-97% |

   - Variant B (r = 9 mm, 10 mm field of view): R = 0.3 gives 20-32 degrees and 47-68%; R = 0.5 gives 11-20 degrees and 68-90%. This is close to ideal uniform illumination (R = 0.3: 19-29 degrees, 52-70%).
   - Averaging the vectors from independent placements helps as expected: for variant A at R = 0.3 the median error falls from 41 to 24, 18 and 15 degrees with 3, 5 and 9 placements, and the no-grain modulation falls from 0.15 to 0.08, 0.06 and 0.05.
   - A golfer marks the ball once per green, so in normal use there is one placement. The real resultant length R of grainy turf is unknown.

8. **Signal level is adequate; timing and energy figures need adjusting.** Confidence: medium for geometry, low for absolute level. Geometry factor for variant A with 5% canopy reflectance and no window loss: 0.166 lux at the detector per millicandela of on-axis LED intensity; variant B: 0.036. The first report's 1-3 lux at 5 mA follows if the LED gives 6-18 mcd at 5 mA, which is plausible but UNVERIFIED. From recollection of the OPT4001 datasheet (UNVERIFIED), a 6.5 ms conversion resolves about 40 mlux in the lowest range, which is 0.5-2% of the signal; 25 ms resolves about 10 mlux. Use 20 mA and 12.7-25 ms or longer. A read then takes 0.8-1.6 s and 24-48 mJ of LED energy, not about 2 mJ. This is still negligible for the battery.

9. **Red to near-infrared normalisation is plausible but unproven.** Confidence: low to medium. The leaf-optics premise is confirmed (finding 5). Whether the ratio cancels tilt on real turf is not: near-infrared light penetrates the canopy, so its response to tilt and relief may differ from red. It needs co-located emitters and a bench test on tilted sod. The near-infrared photocurrent will probably be tens of times the red one (higher LED radiant intensity, about nine times the canopy reflectance, higher photodiode responsivity), so the two bands need separate drive currents or gains.

10. **Local reading against whole-putt grain.** Confidence: medium (reasoning only). The sensor reads surface lean under the marker, which includes the last mowing and rolling pass. Mowing stripes reverse that lean from pass to pass (walk-behind passes about 0.53-0.66 m wide, triplex about 1.5 m; widths from memory, UNVERIFIED). Whether surface lean or growth habit controls ball roll is unknown. Placing the marker may comb the blades.

11. **No off-the-shelf downward imager fits.** Confidence: low (UNVERIFIED, recollection agrees on the PixArt working ranges and the PMW3901 package height). An imager with the same LED ring would remove the uneven-illumination and patchiness problems, but not the basic sample-size limit (ideal uniform case in finding 7).

12. **Humidity sensing is not worth including.** Confidence: low to medium (judgement). Unchanged from the first report.

## 5. Verification table

Verdicts: confirmed (recomputed or checked against a dataset in this session), corrected, contradicted, unverifiable (needs a web source that could not be reached).

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | TI OPT4001 (OPT4001DTSR, OPT4001YMNR): exists, active, in US stock, dimensions, supply, price | unverifiable | none | UNVERIFIED. Reviewer recollection agrees with part numbers, both package sizes, 600 us to 800 ms, 1.6-3.65 V. Not a confirmation. |
| 2 | Vishay VLMS1500-GS08 red 0402 LED | unverifiable | none | UNVERIFIED. Recollection agrees on series and 1.0 x 0.5 x 0.35 mm. Luminous intensity unknown. |
| 3 | TI OPT3001DNPR (fallback detector) | unverifiable | none | UNVERIFIED. Recollection agrees (USON-6 2.0 x 2.0 x 0.65 mm, 100 / 800 ms). |
| 4 | Vishay VEMD8080 and VEMD1060X01 photodiodes (fallback) | unverifiable | none | UNVERIFIED. Recollection agrees on both sizes. |
| 5 | Kingbright APHHS1005SURCK (fallback LED) | unverifiable | none | UNVERIFIED. |
| 6 | Lumex SML-LX0402SIC-TR (fallback LED) | unverifiable | none | UNVERIFIED. |
| 7 | 8-direction roll test as ground truth | corrected | Also record sideways offset; level accurate to about 0.02 degrees | The fit as written yields only the along-track strength. |
| 8 | Prior-based estimate (fallback) | unverifiable | none | Rests on lore (grain runs downhill, toward the setting sun). |
| 9 | a0, Stimp ratio, feet difference, equivalent slope table | confirmed | none | Recomputed. |
| 10 | Cross-grain drift k x D / 2; 25-35% less at firm pace | confirmed | 23-30% less at 0.30-0.43 m past | Mathematics confirmed numerically. Valid only if grain acts as a sideways force; zero for pure direction-dependent resistance. |
| 11 | Single-facet contrast numbers; specular lean 55 degrees | confirmed | none | Centre-point values. Over an 8 mm field of view the 80 degree case falls from 0.49 to 0.26. |
| 12 | Seating tilt gives 5-10% false first harmonic per degree (7% at r = 6, h = 2.2) | corrected | 4.8% per degree at the centre; 6.7% over an 8 mm field of view | Size about right; the derivation (LED height change at fixed offset) is not valid for a rigid tilt. |
| 13 | Tilt-tolerant geometry: aimed LED at 35 degrees, side emitter at h = r / sqrt(3), 0.8% per degree at r = 4.5, h = 2.2 | contradicted | 1.9-2.4%, 2.2-2.9% and 3.5% per degree | False harmonic is about cot(elevation) per radian for any emitter pattern. |
| 14 | Irradiance varies about 7:1 across a 4 mm field of view | corrected | 11:1 (flat chip LED); 141:1 across the recommended 8 mm | 7:1 holds only for an isotropic or aimed source. |
| 15 | Canopy modulation 0.10-0.24 at R = 0.3; accept if above 0.10 | corrected | Signal 0.14-0.25, but no-grain noise 0.10-0.23 median; threshold must come from the measured noise floor | Reviewer's Monte-Carlo; order of magnitude only. |
| 16 | Photopic weights 0.27 (630 nm), 0.06 (660 nm), 0.57 (605 nm) | confirmed | 0.265, 0.061, 0.567 | CIE 1924 table from the colour-science package. |
| 17 | Leaf reflectance and transmittance by band | confirmed | Blue and 660 nm reflectance about 4% | PROSPECT-D run; single leaf. |
| 18 | About 1-3 lux at the detector at 5 mA | unverifiable | Geometry factor 0.166 lux per mcd (variant A) | Consistent if the LED gives 6-18 mcd at 5 mA; LED intensity not checked. |
| 19 | Read takes 0.3-1.2 s and about 2 mJ | corrected | 0.3-1.6 s; 5-48 mJ | Arithmetic. Still negligible. |
| 20 | OPT4001 conversions of 6.5-25 ms are adequate | unverifiable | Reviewer recollection: about 40 mlux step at 6.5 ms; prefer 12.7-25 ms or longer | Needs the datasheet resolution table. |
| 21 | 40-50 facets in a 10 mm field of view, about 7 in 4 mm | unverifiable | 12-20 shoots in 10 mm, 2-3 in 4 mm at 15-25 shoots per cm2 | Arithmetic is right; shoot density is from memory. |
| 22 | Sign convention: down-grain = bright azimuth + 180 degrees | confirmed | none | Facet model and simulation agree; consistent with mowing-stripe appearance. No turf measurement. |
| 23 | Red to near-infrared ratio cancels tilt | unverifiable | none | Premise confirmed by PROSPECT-D; cancellation itself untested. NIR photocurrent likely tens of times red, not 7 times. |
| 24 | No published quantitative grain study; no commercial grain instrument | unverifiable | none | No literature or patent search was possible in either pass. |
| 25 | Stimpmeter release 1.83 m/s; Brede 1991 slope correction; Penner 2002 (5/7) factor | unverifiable | none | The (5/7) g sin(slope) rolling result is standard mechanics. Citations not checked. Energy estimate gives 1.91 m/s at the ramp foot. |
| 26 | No off-the-shelf downward imager fits a 7 mm puck | unverifiable | none | UNVERIFIED part data. |
| 27 | Confidence: 45-60% reads direction on grainy bermudagrass; 25-35% improves the aim line | corrected | Reviewer estimate: 35-55% for a single reading with variant A, 50-70% with variant B or several placements; 15-25% improves the aim line | Judgement, informed by finding 7. |

## 6. Risks

1. No part in the bill of materials for this function has been checked against a datasheet or a distributor page. Part numbers, package heights, lifecycle and stock could all be wrong as of 2026-11-11.
2. The size of the grain effect on ball roll, and above all its sideways component, is unmeasured. A wrong correction is worse than none.
3. A single reading samples a few dozen blades. Sampling noise alone can produce a confident-looking but wrong direction, and it rotates with the turf, so the rotation test does not catch it.
4. Seating tilt and local relief add a false first harmonic of roughly 5-7% per degree for the first report's layout and cannot be removed by LED geometry.
5. Patchy turf (sand topdressing, ball marks, seedheads, disease, dormant or painted bermudagrass) aliases into the first harmonic, made worse by the uneven illumination.
6. Dew, guttation, frost and irrigation water create glints from all directions.
7. The reading is local. Mowing stripes reverse surface lean between passes, and grain near the hole may differ from grain under the marker.
8. Placing, sliding or pressing the marker can comb the blades it then measures.
9. The link between optical modulation and mechanical grain strength is unknown and probably depends on species and maintenance.
10. The recess collects sand, clippings and water. Fouled windows change LED gains between calibrations.
11. A recess of 13-20 mm diameter and about 2.2 mm depth, plus the parts above it, competes with the battery and display for volume in a 6-7 mm puck.
12. Prior art (for example Japanese patents on grain detection, paper fibre-orientation gauges) was not searched. Freedom to operate is unknown.
13. Calling the output a measurement of grain before validation would be a product-claim risk.

## 7. Open questions

1. Re-run this topic with web access to confirm every part number, package height, price, stock level and lifecycle status, and to look for measured with-grain and against-grain ball-roll data.
2. Does grain deflect a cross-grain putt sideways, and by how much relative to its effect on speed? This decides whether the feature can move the aim line at all.
3. What first-harmonic modulation does real turf give at 630 nm and 850 nm, by species and height of cut? What is the no-grain noise floor and the spot-to-spot repeatability at 2-3 cm spacing?
4. What is the blade-alignment resultant length on grainy bermudagrass, on a fresh mowing stripe, and on groomed bentgrass?
5. Does surface lean from mowing and rolling change ball roll, or only growth-habit grain?
6. How flat is the canopy inside an 8-10 mm patch, and how far do blades spring up into the recess?
7. How much sunlight, visible and near-infrared, leaks under the marker to a detector 10-15 mm from the rim?
8. OPT4001: resolution and noise at 6.5, 12.7 and 25 ms conversions. OPT4003-Q1: channel spectra, package, availability.
9. Luminous intensity of the chosen red LED at 5-20 mA and radiant intensity of the near-infrared LED, to set drive currents.
10. Can the stack afford a 20 mm recess (variant B)? Can the user be asked for two or three placements when the reading is weak?
11. Is there patent coverage on multi-azimuth optical grain detection for greens?
12. Leads to check, from the reviewer's memory only and UNVERIFIED: the TI OPT4048 four-channel sensor and the Vishay VEML6031X00 as single-chip dual-band detectors; pulse-oximetry style multi-chip red plus infrared emitters for exact co-location; wafer-level endoscope cameras (OmniVision OVM6948 class) as the only camera type whose focus range starts near 3 mm.

## 8. Sources

No web page was opened in this session. The items below are everything this document rests on.

1. `colour-science` Python package, version 0.4.7, installed from the Python package index in this session. Used for the CIE 1924 photopic luminosity table. Project page (not opened in a browser): https://pypi.org/project/colour-science/
2. `prosail` Python package, version 2.0.5, installed from the Python package index in this session. Used to run the PROSPECT-D leaf optics model. Project page (not opened in a browser): https://pypi.org/project/prosail/
3. Local script `greenline-marker/docs/research/grain-sensing-checks/check_grain.py` (this review): model arithmetic, putt integration, facet contrast, ring-sensor tilt simulation, illumination uniformity, signal level, timing and energy.
4. Local script `greenline-marker/docs/research/grain-sensing-checks/mc_blades.py` (this review): Monte-Carlo blade-sampling model.
5. Sibling document `greenline-marker/docs/research/inertial-sensors.md` (seating estimate of 2-5 mrad, itself an estimate).
6. The first research report on this topic (supplied as JSON to this review). All of its part data and citations came from model memory and carry no URLs.

Attempted and not reached (not sources): `www.ti.com` (OPT4001 product page and datasheet), `www.vishay.com` (0402 LED datasheet), `www.digikey.com` (OPT4001 product page). Four web searches were refused for budget.

Literature named by the first report and not checked (UNVERIFIED citations, no URLs): Brede 1991, Agronomy Journal 83:425; Penner 2002, Canadian Journal of Physics 80:83; Gates et al. 1965, Applied Optics 4:11; Jacquemoud and Baret 1990 (PROSPECT); Vanderbilt and Grant 1985, IEEE Transactions on Geoscience and Remote Sensing; Sandmeier et al. 1998, Remote Sensing of Environment 66:222; Karcher and Richardson 2003, Crop Science; Woodham 1980 (photometric stereo).

## Appendix: models used in the checks

- Putt: point mass with rolling deceleration a0 opposing velocity plus a constant sideways acceleration k x a0; launch speed set so that a straight putt stops at the hole or a stated distance past it; integrated with a 0.1 ms step.
- Ring sensor: detector at the origin with cosine response and a hard-baffled field of view; canopy a plane 2.2 mm below, tilted about the point under the detector; eight emitters (flat Lambertian facing down, Lambertian aimed at the centre, or Lambertian side emitter firing inward); uniform Lambertian canopy for the tilt study, identical leaning Lambertian facets for the lean study; 0.04 mm integration grid. First harmonic defined as 2 x |sum of S_i exp(-j phi_i)| / sum of S_i.
- Blade sampling: point facets at 50 or 100 per cm2, placed at random or on a jittered grid; lean 50-85 degrees from vertical; lean azimuth from a von Mises distribution with the stated resultant length; lognormal facet size; no shadowing, no specular term, no transmission; 30% of the mean signal non-directional; 1500 trials per case.
- Leaf optics: PROSPECT-D with (N, chlorophyll ug/cm2, carotenoid ug/cm2, water cm, dry matter g/cm2) = (1.3, 35, 8, 0.008, 0.004), (1.5, 45, 10, 0.012, 0.006), (1.8, 60, 12, 0.015, 0.009).
