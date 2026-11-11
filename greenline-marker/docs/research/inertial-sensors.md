# GreenLine research: precision tilt sensing (accelerometer / IMU selection and error budget)

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web.

- Web search: all four queries attempted were refused ("web search budget is used up", a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.st.com` and `www.digikey.com` both failed to resolve (hosts outside this session's allowed network domains). No further hosts were tried, as instructed by the tool.

Consequences:

- **No part number, dimension, price, stock level or lifecycle status in this document was confirmed against a live source in this pass.** Every such item is marked UNVERIFIED. They carry forward the first report's values, which that report itself took from search-result extracts, not from opened datasheets.
- What was verified here: all of the first report's arithmetic and derivations (recomputed with a local script), internal consistency between its cited figures, and the engineering logic. Several corrections came out of that and are listed in section 6.
- Where the reviewer's own recollection of a datasheet (model training data, up to about mid-2026) agrees or disagrees with the report, that is stated as "reviewer recollection". Recollection is not a source and does not change an UNVERIFIED mark.

Before design freeze, a person or a follow-up session with network access must open the ST and ADI datasheets and the live DigiKey / Mouser / Newark / Arrow product pages for the two recommended parts and the fallback. Hosts that need to be allowed: `www.st.com`, `estore.st.com`, `www.analog.com`, `www.digikey.com`, `www.mouser.com`, `www.newark.com`, `www.arrow.com`, `invensense.tdk.com`, `www.bosch-sensortec.com`, `www.murata.com`.

## 1. Summary

The first report's central conclusions survive the checks that could be made:

1. Sensor noise is not the limit. Using the reported noise densities, every candidate averages to 0.01-0.21 mrad in one second. The arithmetic is correct.
2. Offset temperature coefficient and long-term offset drift are what separate the parts. With the reported figures, only the ST IIS2ICLX gets near the 0.2-0.5 mrad target without heavy compensation. The arithmetic is correct, and the two IIS2ICLX tempco figures are internally consistent with the ST design-tip figures the report quotes (8 mg at 25 C rising to 14 mg at 105 C is exactly 0.075 mg/C over 80 C).
3. Seating of a 40 mm puck on a turf canopy (estimated 2-5 mrad per placement) is far worse than any sensor error, so the puck's own tilt is only a coarse local slope sample. The geometry is correct; the 2-5 mrad figure remains an estimate with no published data behind it and may be optimistic.
4. A user flip calibration is required and must not be done on turf. The derivation (bias error = |t| x sin(delta/2)) is correct.

Corrections and additions from this review:

- The 0.1-0.25 mrad "after flip calibration" figure is optimistic. It assumes a flip-calibration residual of 0.03-0.05 mrad, which needs the three base pads to reseat within about 1.4 um. On a consumer surface or a cradle with dust, 5-10 um is more realistic, giving 0.2-0.35 mrad total. A realistic working figure for the IIS2ICLX path is 0.25-0.5 mrad.
- The factory temperature-calibration acceptance test is invalid as written: a quadratic fitted through three temperature points has zero residual by construction. At least five points, or a continuous up-and-down ramp, are needed.
- The report says gyro tracking "does not rescue" the flip calibration. That is true on turf, but on a hard surface a gyro-measured flip yaw does help: the bias error becomes about |t| x epsilon / 2, where epsilon is the yaw measurement error.
- The 18 um camera-to-accelerometer figure is correct but is not the tightest alignment. Camera pitch boresight stability of 0.5 mrad is about 0.3 pixel for a typical micro camera, and a through-thickness temperature difference of 5 C in a printed nylon puck could bow the enclosure enough to move rim-mounted cameras by about 1.5 mrad relative to the centre unless cameras and accelerometer share one rigid board.
- Base pads 0.05-0.10 mm proud cannot be held by 3D-printing tolerances. They must be hard inserts or a machined feature.
- Given the above, the system requirement should be stated as 1 mrad (0.1% slope), with the IIS2ICLX kept in the first build for margin.

## 2. Final recommendation

Architecture (unchanged from the first report, with amendments):

- **Primary gravity reference: ST IIS2ICLXTR** (2-axis in-plane digital inclinometer, reported 5 x 5 x 1.7 mm ceramic LGA-16). Mounted flat on the main board near its centre so X and Y lie in the base plane. UNVERIFIED on stock, price and lifecycle in this pass.
- **Companion 6-axis IMU: ST LSM6DSV16XTR** (reported 2.5 x 3.0 x 0.83 mm LGA-14L) for stillness detection, flip-yaw measurement, gestures, wake-on-motion, face-up/down detection and a cross-check on the precision part. UNVERIFIED on stock, price and the +/-0.07 mg/C tempco row.
- **Fallback precision part: Analog Devices ADXL355BEZ-RL** (US-headquartered maker; reported 6 x 5.6 x 2.2 mm ceramic LCC, 3-axis). Use if the IIS2ICLX becomes unavailable or a US-HQ maker is required. Its lifecycle signal at Mouser, reported by the first agent, needs to be resolved with ADI. UNVERIFIED.
- **Cost-down option: LSM6DSV16X alone** with per-unit temperature compensation, for an estimated 0.5-1 mrad. Lay out both footprints; populate the IIS2ICLX for the first engineering build and decide whether to keep it using field data.
- **Alternate companion IMUs:** Bosch BMI270 or TDK ICM-45686 on the same 2.5 x 3 mm LGA-14 outline. Pin compatibility must be checked against the datasheets before sharing a footprint. UNVERIFIED.
- **Magnetometer:** optional, unpopulated footprint for a Bosch BMM350. Not needed for the aim line. Do not fit a magnet or steel plate in the product if it is populated.

Requirement:

- State the gravity-reference requirement as 1 mrad (0.1% slope) maximum, with a design target of 0.25-0.5 mrad. The original 0.2-0.5 mrad figure is tighter than the camera chain and the enclosure are likely to support.
- Take slope and fall line mainly from the gravity-referenced cameras or from several averaged placements. Treat the puck's own tilt as a coarse local sample, improved by a 180 degree spin-and-reread.

Mechanical and layout:

- Cameras and the precision accelerometer on one rigid FR-4 board (or a common metal stiffener). Mount that board to the printed enclosure at three points so enclosure warp does not bend it.
- Symmetric copper and component layout around the IIS2ICLX. Keep it away from the BLE module, charger, battery tabs and fastener bosses. No potting over it.
- Base: flat annular land at full diameter for turf, recessed centre for the grain sensor, and three hard pads for hard-surface seating. Make the pads pressed-in hard inserts (for example stainless or ceramic pins set to height on a fixture) or machine the base after printing. Printed pads at 0.05-0.10 mm are below print tolerance.

Factory calibration, after final assembly and thermal cycling:

1. Six-face tumble of the IMU for offset, scale and cross-axis.
2. IIS2ICLX scale and cross-axis from tilted poses, taken at the same full-scale setting that will be used in operation. If operating at +/-0.5 g, use poses of about +/-20 degrees, since +/-1 g poses saturate that range.
3. Four-yaw read (0/90/180/270 degrees) on a granite flat for the lumped device-frame bias.
4. Temperature calibration with at least five points across about 0-55 C, or a slow ramp up and down, with a 0/180 degree pair at each point. Fit a quadratic and judge the unit on the residual at points not used in the fit and on the up/down difference (hysteresis).
5. Camera-to-gravity boresight (pitch and roll) against a levelled target.

User calibration:

- A keyed charging cradle with 0 and 180 degree positions on a hard, flat, cleanable seat is the preferred method. Firmware should reject a pair if the two reads disagree with the stored bias by more than a set threshold (dust under a pad shows up this way) and should log bias against temperature.
- Without a cradle: a hard surface within about 10 mrad of level, with the flip yaw measured by the gyro and used in the bias solution.
- Never on turf.
- On the green, the optional precision read is place, read, spin 180 degrees in place, read. This cancels all device-frame bias, including base-plane tolerance, and averages two seatings.

## 3. Candidate table

All specification, price, stock and lifecycle entries are the first report's values (taken by that agent from search-result extracts). None was re-confirmed against a live source in this pass: treat every cell as UNVERIFIED. The "Reviewer recollection" column records whether the reviewer's memory of the datasheet agrees; it is not a source.

| Name | MPN | Maker / HQ | Key specs (as reported) | Dimensions mm (as reported) | Interface / supply | Price (as reported) | US distributors / stock (as reported) | Lifecycle (as reported) | Reviewer recollection | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ST IIS2ICLX 2-axis inclinometer | IIS2ICLXTR | STMicroelectronics / Switzerland (Geneva; incorporated in the Netherlands) | +/-0.5/1/2/3 g; 15 ug/rtHz; offset tempco typ +/-0.020, max +/-0.075 mg/C; zero-g offset about 8 mg; life drift about 2.5 mg (AN5551); -40..105 C | 5 x 5 x 1.7 ceramic-cavity LGA-16 | SPI / I2C; 1.71-3.6 V; about 0.42 mA | $30.76 at 1, $28.55 at 10-24 (ST eStore); $33.55 (DigiKey) | ST eStore in stock; DigiKey 5,125; Newark 2,829; Verical 2,378 | Active (implied) | Agrees on package, noise, <0.075 mg/C, full-scale ranges, supply, 0.42 mA, 0.015 mg/LSB at +/-0.5 g. 0.020 typ: moderate confidence. No knowledge of current stock or price. | Recommended (primary). UNVERIFIED |
| ST LSM6DSV16X 6-axis IMU | LSM6DSV16XTR | STMicroelectronics / Switzerland | Accel offset +/-12 mg; tempco +/-0.07 mg/C; noise about 60 ug/rtHz (report: from memory) | 2.5 x 3.0 x 0.83 LGA-14L | SPI / I2C (also MIPI I3C per reviewer recollection); supply not checked by report | $2.78 at 5,000 reel (DigiKey); about $4.38 at 1 (Mouser via aggregator) | DigiKey listing, stock not seen; Mouser 51 (aggregator); regional pages mixed | Active (ST page) | Agrees on package, 60 ug/rtHz, +/-12 mg, 1.71-3.6 V supply. No firm recollection of the +/-0.07 mg/C row; earlier ST IMUs of this family are +/-0.1 mg/C. | Recommended (companion; cost-down sole sensor). UNVERIFIED |
| ADI ADXL355 3-axis accelerometer | ADXL355BEZ-RL (also -RL7, ADXL355BEZ tray) | Analog Devices / USA (Wilmington, MA) | 22.5 ug/rtHz; tempco 0.15 mg/C max; offset +/-25 typ, +/-75 max mg; repeatability +/-2 mg X/Y over 10 years; 200 uA; 20-bit | 6 x 5.6 x 2.2 ceramic LCC-14 (older revisions 6 x 6 x 2.1) | SPI / I2C; 2.25-3.6 V (report: from memory) | $77.41 at 1 (DigiKey, -RL7); GBP 52.56 at 1, GBP 39.28 at 2,000 (DigiKey UK, -RL) | DigiKey: -RL7 backorder, -RL 1,770; Mouser notice "will no longer be carrying this item" for ADXL355BEZ | Production per aggregator; own status not confirmed | Agrees on noise (25 in early revisions, 22.5 later), tempco, offset, current, supply, interfaces, order codes, and both package descriptions. No knowledge of a discontinuation. | Fallback (precision). UNVERIFIED |
| TDK ICM-45686 6-axis IMU | ICM-45686 | TDK InvenSense / Japan (InvenSense in San Jose, USA) | Accel 70 ug/rtHz; tempco +/-0.15 mg/C | 2.5 x 3 x 0.81 LGA-14 | 1.71-3.6 V; I2C / I3C / SPI (report: from memory) | $3.82 at 1 (DigiKey cached) | DigiKey out of stock, 45-week lead time (possibly stale) | Active (DigiKey) | Agrees on package and noise. No recollection of price or the tempco row. | Fallback (alternate companion). UNVERIFIED |
| Bosch BMI270 6-axis IMU | BMI270 | Bosch Sensortec / Germany | Offset +/-20 mg; tempco +/-0.25 mg/K; about 160 ug/rtHz | 2.5 x 3.0 x 0.83 LGA-14 | Not checked by report (reviewer recollection: SPI / I2C, VDD 1.71-3.6 V, VDDIO 1.2-3.6 V) | $4.23 at 1 (DigiKey) | DigiKey 32,340 | Active (third-party site) | Agrees on package, noise, offset, tempco. | Viable (companion only). UNVERIFIED |
| TDK ICM-42688-P | ICM-42688-P | TDK InvenSense / Japan | 70 ug/rtHz; offset +/-20 mg; tempco not confirmed | 2.5 x 3 x 0.91 LGA-14 | Not checked | Not seen | DigiKey out of stock, 45 weeks (possibly stale) | Active (DigiKey) | Agrees on package, noise; recollects +/-0.15 mg/C. | Viable (footprint alternate). UNVERIFIED |
| TDK IIM-42652 | IIM-42652 | TDK InvenSense / Japan | +/-2..16 g; -40..105 C; 70 ug/rtHz (medium) | 2.5 x 3 x 0.91 LGA-14 | Not checked | Not seen | DigiKey listing | Not confirmed | Agrees on package and temperature range. | Viable, no benefit. UNVERIFIED |
| Bosch BMI323 | BMI323 | Bosch Sensortec / Germany | Offset +/-50 mg; tempco +/-0.3 mg/K; 180 ug/rtHz | 2.5 x 3.0 x 0.83 LGA | Not checked | Not seen | Mouser page | Not confirmed | Agrees on package and noise. | Viable (gyro/gesture only). UNVERIFIED |
| Murata SCL3300-D01 inclinometer | SCL3300-D01-1 | Murata / Japan (MEMS unit in Finland) | Offset +/-20 mg; offset temperature dependency +/-10 mg over -40..125 C; 0.0012 deg/rtHz | 8.6 x 7.6 x 3.3 | SPI; 3.0-3.6 V; 1.2 mA | EUR 33.20 at 1 (DigiKey Italy) | DigiKey 1,610 (Italy view); Newark; Mouser | Active | Agrees on package size, supply, current, interface. | Rejected on size. UNVERIFIED |
| Murata SCL3400-D01 | SCL3400-D01-1 | Murata / Japan | 0.0009 deg/rtHz | 8.6 x 7.6 x 3.3 | SPI; 3.0-3.6 V | Not seen | DigiKey, 17-week lead time | Active | Agrees on package size. | Rejected on size. UNVERIFIED |
| ADI ADXL354 (analog) | ADXL354BEZ | Analog Devices / USA | Analog output, about 20 ug/rtHz | Same LCC-14 as ADXL355 | Analog; needs ADC | Not seen | US stock not seen | Recommended for New Designs (ADI page) | Agrees. | Rejected (needs ADC). UNVERIFIED |
| ADI ADXL357 | not given | Analog Devices / USA | Report: from memory, +/-10/20/40 g, about 80 ug/rtHz | Not verified | Not checked | Not checked | Not checked | Not checked | Agrees with the from-memory values. | Rejected (high-g). UNVERIFIED |
| ADI ADXL367 | not given | Analog Devices / USA | 170 ug/rtHz; 0.25 mg/LSB | 2.2 x 2.3 x 0.87 | Not checked | Not checked | Not checked | Not checked | Agrees on package. | Rejected (wake sensor). UNVERIFIED |
| ST IIS3DHHC | IIS3DHHCTR | STMicroelectronics / Switzerland | +/-2.5 g; 45 ug/rtHz; <0.4 mg/C | 5 x 5 x 1.7 ceramic LGA-16 | Not checked | Not seen | DigiKey listing | Obsolete (ST page) | Agrees on specs. No knowledge of the obsolescence. | Rejected. UNVERIFIED |
| ST IIS3DWB | IIS3DWBTR | STMicroelectronics / Switzerland | 75 ug/rtHz; tempco +/-1 mg/C | 2.5 x 3.0 x 0.83 LGA-14L | Not checked | Not checked | Not checked | Active (implied) | Agrees on package and noise. | Rejected (vibration part). UNVERIFIED |
| ST LSM6DSO32 | LSM6DSO32TR | STMicroelectronics / Switzerland | Not retrieved | 2.5 x 3.0 x 0.83 LGA-14L | Not checked | Not checked | Not checked | Active (sibling) | - | Rejected (high-g). UNVERIFIED |
| Bosch BMA456 | BMA456 | Bosch Sensortec / Germany | 120 ug/rtHz; tempco 0.2-0.35 mg/K | 2 x 2 x 0.65 | Not checked | Not checked | Not checked | Not confirmed | Agrees on package. | Rejected. UNVERIFIED |
| Bosch BMA580 | BMA580 | Bosch Sensortec / Germany | Offset +/-50 mg; tempco +/-0.2 mg/K; 120 ug/rtHz | 1.2 x 0.8 x 0.55 WLCSP | Not checked | Not seen | Mouser page | Not confirmed | Agrees on package. | Rejected. UNVERIFIED |
| Kionix KX134-1211 | KX134-1211 | Kionix (ROHM group) / USA; parent Japan | +/-8..64 g; 300 ug/rtHz | 2 x 2 x 0.9 LGA-12 | Not checked | Not seen | TTI (End of Life) | End of Life / Last Time Buy | Agrees on package and ranges. No knowledge of the EOL notice. | Rejected. UNVERIFIED |
| Memsic MXC4005XC | MXC4005XC | Memsic / China | 12-bit thermal accelerometer; drift not found | 1.18 x 1.70 x 0.85 WLP-6 | I2C; 1.62-3.6 V | Not seen | DigiKey Active, 12-week lead time | Active | Agrees it is a 12-bit thermal part. | Rejected. UNVERIFIED |
| NXP FXLS8974CF | FXLS8974CFR3 | NXP / Netherlands (pages reported on st.com) | Tempco about 0.55 mg/C; 217 ug/rtHz; 12-bit | 2 x 2 x 0.95 DFN-10 | Not checked | Not seen | Mouser page | Not confirmed | Agrees on package. ST announced in 2025 an agreement to buy NXP's MEMS sensor business, which would explain the st.com pages. | Rejected. UNVERIFIED |
| TDK ICM-42670-P | not given | TDK InvenSense / Japan | Not researched | Not verified | - | - | - | - | - | Rejected (not evaluated). UNVERIFIED |
| Bosch BMM350 magnetometer | BMM350 | Bosch Sensortec / Germany | TMR; 190 nT rms X/Y, 450 nT Z; +/-2000 uT; 200 uA at 100 Hz | 1.28 x 1.28 x 0.5 WLCSP | Not stated | $2.26 at 1 (DigiKey) | DigiKey 130,544 | Active | Agrees on package, noise, range, current. | Viable (optional, unpopulated). UNVERIFIED |
| Memsic MMC5983MA magnetometer | MMC5983MA | Memsic / China | AMR; 0.4 mG rms; 0.5 deg heading; +/-8 G; 18-bit | 3.0 x 3.0 x 1.0 LGA | Not stated | $3.32 at 1 (DigiKey via aggregator) | DigiKey about 41,361 | Active | Agrees on all listed specs. | Viable (optional alternate). UNVERIFIED |
| Base geometry A: annular land + three hard pads + recessed centre | n/a | design feature | Land OD about 42, ID 32-34; pads 0.05-0.10 proud | n/a | n/a | n/a | n/a | n/a | Sound in principle. Pad height is below print tolerance: use inserts or machining. | Recommended with that change |
| Base geometry B: full flat disc | n/a | design feature | Whole underside flat | n/a | n/a | n/a | n/a | n/a | Conflicts with grain-sensor recess. | Viable |
| Base geometry C: three raised feet | n/a | design feature | Feet of 1 mm or more | n/a | n/a | n/a | n/a | n/a | Agrees feet sink unevenly in turf. | Rejected |

## 4. Key findings, with confidence

Confidence here means confidence after this review. "Arithmetic confirmed" means recomputed locally. Input values from datasheets remain UNVERIFIED.

1. **Noise is not the limit.** One-second boxcar average of white noise is noise density x sqrt(0.5 Hz). Recomputed: IIS2ICLX 0.011 mrad, ADXL355 0.016, SCL3300 0.015, LSM6DSV16X 0.042 (using 60 ug/rtHz), ICM-4xxxx 0.050, BMA456/BMA580 0.085, BMI270 0.113, BMI323 0.127, FXLS8974CF 0.153, KX134 0.212. Arithmetic confirmed. Wording correction: the summary's "<=0.15 mrad for all but the KX134" is slightly wrong because the FXLS8974CF is 0.153; "below 0.2 mrad" is right. Confidence: high for the conclusion, medium for individual inputs.

2. **Offset tempco is the discriminator.** Tempco x 20 C, recomputed: IIS2ICLX 0.4 (typ) / 1.5 (max) mrad; LSM6DSV16X 1.4; ADXL355 3.0 (max); ICM-45686 3.0; BMA580 4; BMI270 5; BMI323 6; IIS3DHHC 8; FXLS8974CF 11; IIS3DWB 20. Arithmetic confirmed. Note that 20 C is a mid case: a unit calibrated indoors at about 22 C and used at 5 C on a cold morning or at 50 C in direct sun sees about 30 C, which is 0.6 / 2.25 mrad for the IIS2ICLX uncompensated. Confidence: medium (inputs unverified).

3. **IIS2ICLX tempco figures are internally consistent.** The report quotes an ST design tip giving +/-8 mg at 25 C and +/-14 mg at 105 C. 8 + 0.075 x 80 = 14.0 mg, which matches the reported datasheet maximum of 0.075 mg/C. This is a consistency check between two of the report's cited documents, not an independent source. Confidence: medium.

4. **Estimated error after compensation and flip calibration.** The report's root-sum-square of its own terms (0.011, 0.03-0.05, 0.1-0.2, 0.1, 0.03, 0.03 mrad) is 0.15-0.23 mrad; arithmetic confirmed, though the stated lower bound of 0.1 is not supported by those terms. The flip-calibration term is optimistic (see finding 6). With a 0.1-0.2 mrad flip residual the total is 0.21-0.27 mrad. Working figure: 0.25-0.5 mrad for the IIS2ICLX, reviewer estimate. Confidence: low.

5. **Flip calibration is mandatory and its geometry matters.** With poses a1 = t + b and a2 = -R(delta) t + b, the bias error from taking the mean is |t| x sin(delta/2). Recomputed: 30 mrad surface with 5 degree flip error gives 1.31 mrad; with 1 degree, 0.26 mrad; 10 mrad surface with 1 degree, 0.087 mrad. Derivation and numbers confirmed. If the gyro measures the flip yaw and the firmware solves for t and b with that angle, the residual is about |t| x epsilon / 2: a 1% gyro scale error (1.8 degrees on 180) gives 0.47 mrad on a 30 mrad surface and 0.16 mrad on a 10 mrad surface; a gyro scale calibrated to 0.2% gives under 0.1 mrad at 30 mrad. So gyro yaw measurement is useful on hard surfaces. It does nothing for turf seating noise. Confidence: high for the derivation.

6. **Hard-surface seating repeatability limits the flip calibration.** Reviewer estimate: three pads on a 19 mm radius form a triangle 28.5 mm high. A height error at one pad of 1.4 um tilts the puck 0.05 mrad; 5 um gives 0.18 mrad; 20 um (a dust grain) gives 0.70 mrad. The report's 0.03-0.05 mrad flip residual therefore needs micrometre-level reseating. A cradle with a hard, clean seat might reach 2-5 um (0.07-0.18 mrad); an arbitrary table will be worse. Confidence: medium (geometry certain, cleanliness assumptions are estimates).

7. **Long-term drift is mg-class.** Reported: IIS2ICLX about 2.5 mg over life, ADXL355 +/-2 mg over 10 years, consumer IMUs +/-20 to +/-50 mg. These are 5 to 250 times a 0.2-0.5 mrad budget (the report says 5-100; +/-50 mg against 0.2 mrad is 250). The sqrt-time scaling of the ADXL355 figure to +/-1 mg at 2.5 years is arithmetically right; whether the datasheet supports that scaling is UNVERIFIED. Confidence: medium.

8. **Turf seating is the dominant error for the puck's own tilt.** 0.1 mm across 34 mm is 2.94 mrad; the same 0.1 mm under a 914 mm level is 0.11 mrad. Arithmetic confirmed. The reported BreakMaster accuracy of +/-0.2 degrees is 3.49 mrad. The 2-5 mrad per-placement estimate is plausible and could be low: ball marks, footprints, topdressing sand and grain can give more than 0.1 mm of local height difference. No published data was found by the first agent and none could be searched for here. Confidence: medium for the direction, low for the number.

9. **Camera path and the real requirement.** Camera-derived slope equals the gravity-referenced elevation angle plus h/d (4 mm lens height at 3 m is 1.3 mrad), so accelerometer error maps 1:1 into slope error and is independent of seating. Confirmed as reasoning. 0.5 mrad over 36 mm is 18 um; confirmed. Two further alignment terms the report did not include, both reviewer estimates: (a) camera pitch boresight: for an assumed micro camera of about 60 degrees across 640 pixels, one pixel is 1.6 mrad, so 0.5 mrad is 0.3 pixel, which a plastic-lens module may not hold over temperature; (b) thermal bowing: curvature = CTE x delta-T / thickness, so a 6 mm printed nylon puck (CTE about 100 ppm/K) with 5 C between top and bottom bows 0.083 per metre, tilting a rim-mounted camera at 18 mm radius by 1.5 mrad relative to the centre. The same calculation for a 0.8 mm FR-4 board with 0.2 C across it gives 0.07 mrad, which is why cameras and accelerometer need a common rigid board that the enclosure cannot bend. Confidence: medium.

10. **Murata SCL3300 / SCL3400 do not fit.** Reported package 8.6 x 7.6 x 3.3 mm. Matches reviewer recollection. UNVERIFIED in this pass. Confidence: medium-high.

11. **Magnetometer value is modest.** 2% slope x sin(5 degrees) = 0.17% and x sin(2 degrees) = 0.07%; confirmed. Horizontal field across the continental US of about 16-26 uT follows from total field 45-55 uT and inclination 55-73 degrees (reviewer physics estimate), consistent with the report's 15-30 uT. BMM350 noise of 190 nT on a 20 uT horizontal field is about 0.5 degrees rms. Confidence: medium.

12. **Assembly stress.** The quoted ADI guidance (offset shift of up to a few mg from soldering, symmetric layout, no potting) matches reviewer recollection of the ADI article. UNVERIFIED in this pass. Confidence: medium.

13. **Lifecycle and supply flags.** IIS3DHHC obsolete, KX134-1211 end-of-life, ADXL355 mixed distributor signals, TDK parts out of stock at DigiKey: all UNVERIFIED. None affects the two recommended parts, but the ADXL355 fallback depends on resolving its status.

## 5. Verification table

Verdict key: confirmed = recomputed or logically checked here; corrected = the report's value or wording needs changing; contradicted = evidence found against it; unverifiable = needs a live source that could not be reached in this pass.

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | IIS2ICLXTR exists, is active and purchasable from US distributors today | unverifiable | - | UNVERIFIED. Reviewer recollection: IIS2ICLXTR is ST's tape-and-reel order code for the IIS2ICLX. Stock and status need a live check. |
| 2 | IIS2ICLX package 5 x 5 x 1.7 mm ceramic-cavity LGA-16 | unverifiable | - | UNVERIFIED. Matches reviewer recollection of the ST datasheet. |
| 3 | IIS2ICLX noise 15 ug/rtHz | unverifiable | - | UNVERIFIED. Matches reviewer recollection. |
| 4 | IIS2ICLX offset tempco typ +/-0.020, max +/-0.075 mg/C | unverifiable | - | UNVERIFIED. The max figure is consistent with the quoted 8 mg to 14 mg rise over 80 C (0.075 mg/C exactly). |
| 5 | IIS2ICLX interface and supply: SPI / I2C, 1.71-3.6 V, about 0.42 mA | unverifiable | - | UNVERIFIED. Matches reviewer recollection. |
| 6 | IIS2ICLX price about $30 at qty 1; DigiKey 5,125, Newark 2,829 in stock | unverifiable | - | UNVERIFIED. No recollection can stand in for a live price or stock check. |
| 7 | LSM6DSV16XTR exists, is active and purchasable | unverifiable | - | UNVERIFIED. Reviewer recollection: valid ST order code. The report itself saw mixed regional stock. |
| 8 | LSM6DSV16X package 2.5 x 3.0 x 0.83 mm LGA-14L | unverifiable | - | UNVERIFIED. Matches reviewer recollection. |
| 9 | LSM6DSV16X accel offset +/-12 mg, tempco +/-0.07 mg/C, noise about 60 ug/rtHz | unverifiable | - | UNVERIFIED. +/-12 mg and 60 ug/rtHz match reviewer recollection. The +/-0.07 mg/C row is not recalled; check the datasheet table. If it is +/-0.1 mg/C, the 20 C figure becomes 2.0 mrad. |
| 10 | LSM6DSV16X price $2.78 at 5,000, about $4.38 at 1 | unverifiable | - | UNVERIFIED. |
| 11 | ADXL355BEZ-RL exists; lifecycle status; Mouser "will no longer be carrying" notice | unverifiable | - | UNVERIFIED. Order codes ADXL355BEZ, -RL and -RL7 match reviewer recollection. Reviewer has no knowledge of a discontinuation. Resolve with ADI before relying on it as fallback. |
| 12 | ADXL355 package 6 x 5.6 x 2.2 mm LCC-14 | unverifiable | - | UNVERIFIED. Reviewer recollection: early datasheet revisions state 6 x 6 x 2.1 mm, later ones 6 x 5.6 x 2.2 mm. Design for 2.2 mm height. |
| 13 | ADXL355 specs: 22.5 ug/rtHz, 0.15 mg/C max, +/-25 / +/-75 mg offset, 200 uA, 2.25-3.6 V, SPI / I2C | unverifiable | - | UNVERIFIED. All match reviewer recollection. |
| 14 | ADXL355 price $77.41 at 1 (DigiKey) | unverifiable | - | UNVERIFIED. |
| 15 | ICM-45686: 2.5 x 3 x 0.81 mm, 70 ug/rtHz, +/-0.15 mg/C, $3.82, 45-week lead time | unverifiable | - | UNVERIFIED. Package and noise match reviewer recollection; price, tempco and lead time not recalled. |
| 16 | Base geometry A: pads 0.05-0.10 mm proud, land coplanar within 0.05 mm | corrected | Hard inserted pads or post-machined base; do not rely on printed features at this size | Typical service-bureau print tolerances are a few tenths of a millimetre (reviewer recollection, UNVERIFIED). A pad-plane to land-plane tilt of 0.1 mm over 30 mm is 3.3 mrad of device-frame bias for turf readings, removed only by the spin-and-reread. |
| 17 | One-second averaged noise figures for all candidates | confirmed | - | Recomputed; all match to rounding. Formula is correct for white noise. Inputs UNVERIFIED. |
| 18 | "Every candidate except the KX134 averages to <=0.15 mrad" | corrected | "below 0.2 mrad" (FXLS8974CF is 0.153) | Wording only; no effect on the conclusion. |
| 19 | Tempco x 20 C figures for all candidates | confirmed | - | Recomputed; all match. Add a 30 C case: IIS2ICLX 0.6 typ / 2.25 max mrad. |
| 20 | SCL3300 +/-10 mg = +/-0.57 degrees; 0.06-0.1 mg/C if linear; 1.2-2 mrad over 20 C | confirmed | - | Recomputed. Input UNVERIFIED. |
| 21 | Compensated IIS2ICLX total 0.1-0.25 mrad after flip calibration | corrected | 0.25-0.5 mrad working figure (0.21-0.27 mrad with a 0.1-0.2 mrad flip residual; more on an uncontrolled surface) | The RSS arithmetic is right (0.15-0.23), but the 0.03-0.05 mrad flip residual needs about 1.4 um pad reseating. Reviewer estimate. |
| 22 | Flip-calibration bias error = |t| x sin(delta/2); 1.3 / 0.26 / <0.1 mrad examples | confirmed | - | Derived independently; numbers match. |
| 23 | "Gyro-tracking the flip does not rescue it" (1% cross-axis of 180 degrees = 1.8 degrees = 31 mrad) | corrected | On a hard surface, gyro-measured yaw reduces the error to about |t| x epsilon / 2 (0.16 mrad at 10 mrad slope with 1% scale error) | The 1.8 degree / 31 mrad arithmetic is right and it is true that the gyro cannot carry tilt through the flip. But the gyro's job is to measure yaw, where it helps. On turf nothing rescues it. |
| 24 | Long-term drift is 5-100 times the budget | corrected | 5-250 times for the parts listed | 2.5 mg / 0.5 mrad = 5; 50 mg / 0.2 mrad = 250. Inputs UNVERIFIED. |
| 25 | Seating geometry: 0.1 mm / 34 mm = 2.9 mrad; 0.1 mm / 914 mm = 0.11 mrad; +/-0.2 degrees = 3.5 mrad | confirmed | - | Recomputed. The 2-5 mrad per-placement estimate stays an estimate and may be optimistic. BreakMaster and app accuracy claims UNVERIFIED. |
| 26 | Requirement is 7-17 times tighter than commercial green readers | confirmed | - | 3.49 / 0.5 = 7.0; 3.49 / 0.2 = 17.5. |
| 27 | 0.5 mrad = 18 um across a 36 mm baseline | confirmed | - | Correct but incomplete: camera pitch boresight (about 0.3 pixel) and enclosure thermal bow (about 1.5 mrad at the rim for 5 C through-thickness in printed nylon) are tighter constraints. Reviewer estimates. |
| 28 | Factory temperature calibration: quadratic fit at "three or more" points, accept at 0.1 mg residual | corrected | At least five points or an up/down ramp; judge on held-out points and hysteresis | A quadratic through three points has zero residual by construction, so the acceptance test would pass every unit. |
| 29 | IIS2ICLX scale calibration with +/-1 g edge-on poses | corrected | Calibrate scale at the operating full-scale setting; at +/-0.5 g use about +/-20 degree poses | +/-1 g saturates the +/-0.5 g range. Whether sensitivity matches between full-scale settings is UNVERIFIED, so do not assume it. |
| 30 | Magnetometer heading arithmetic (5 degrees gives 0.17% at 2% slope; 16 steps = 22.5 degrees) | confirmed | - | Recomputed. US horizontal field 15-30 uT is consistent with a physics estimate of 16-26 uT. |
| 31 | SCL3300 / SCL3400 package 8.6 x 7.6 x 3.3 mm | unverifiable | - | UNVERIFIED. Matches reviewer recollection. |
| 32 | BMM350 1.28 x 1.28 x 0.5 mm, $2.26, 130,544 in stock | unverifiable | - | UNVERIFIED. Package matches reviewer recollection. |
| 33 | Lifecycle flags: IIS3DHHC obsolete; KX134-1211 end-of-life; TDK parts 45-week lead time | unverifiable | - | UNVERIFIED. None affects the recommended parts. |
| 34 | Maker HQ countries (ST Switzerland, ADI USA, TDK Japan, Bosch Germany, Murata Japan, NXP Netherlands, Memsic China, Kionix USA under ROHM Japan) | unverifiable | - | No source opened in this pass. All match general knowledge. ST is headquartered in Geneva and incorporated in the Netherlands. |
| 35 | LSM6DSV16X, ICM-45686 and BMI270 share one footprint | unverifiable | - | UNVERIFIED. Same package outline is likely; main pin functions on these LGA-14 IMUs are broadly aligned by reviewer recollection, but auxiliary pins differ. Check each datasheet pin table. |
| 36 | FXLS8974CF pages now on st.com | unverifiable | - | UNVERIFIED. Plausible: by reviewer recollection ST announced in 2025 an agreement to acquire NXP's MEMS sensor business. |

## 6. Corrections to carry into the design

1. Requirement: gravity reference 1 mrad maximum, 0.25-0.5 mrad target. Do not promise 0.1-0.25 mrad.
2. Temperature calibration: five or more points, or a ramp in both directions; validate on points not used for the fit.
3. Flip calibration: cradle seat must be hard, flat and cleanable; firmware must detect an inconsistent pair. Use gyro yaw in the solution when there is no cradle.
4. Scale calibration at the operating full-scale setting.
5. Cameras and precision accelerometer on one rigid board, mounted at three points.
6. Base pads as hard inserts or machined features.
7. Temperature design case of about 30 C from the calibration temperature, not 20 C.

## 7. Risks

- **Nothing was web-verified in this pass.** Stock, price and lifecycle for IIS2ICLXTR, LSM6DSV16XTR and ADXL355BEZ-RL must be checked live before the bill of materials is frozen.
- IIS2ICLX is a single-source part at a reported price of about $30 in small quantity. That is a large share of the bill of materials for a ball marker.
- The reported LSM6DSV16X supply picture was mixed (low stock on some regional pages). UNVERIFIED.
- The reported Mouser notice on the ADXL355 is unexplained. If the part is being withdrawn there is no small US-HQ precision fallback in this list.
- Turf seating (estimated 2-5 mrad, possibly more) dominates any slope taken from the puck's own tilt.
- A flip calibration on turf, or on a hard surface with dust under a pad, injects error from a few tenths of a milliradian to milliradians.
- Long-term offset drift is mg-class, so accuracy degrades to 1-3 mrad if users skip recalibration.
- Direct sun and pocket-to-turf transients create thermal gradients that an oven calibration does not model. The enclosure-bow estimate above (about 1.5 mrad at the rim for 5 C through-thickness) suggests this could be the largest term in the camera path.
- Camera boresight stability over temperature may be worse than the accelerometer error; that belongs to the camera workstream but sets how much accelerometer precision is useful.
- Solder and assembly stress shifts offset by up to a few mg (reported from ADI), so calibration before final assembly is invalid.
- 3D-print tolerances do not support the base flatness and pad heights proposed without a secondary operation.
- A magnetometer, if fitted, is easily corrupted by magnets or steel in or near the product.
- Rules of golf: the first report notes that slope-measuring devices are not permitted during a round. By reviewer recollection this falls under Rule 4.3. UNVERIFIED in this pass; it affects how the product can be positioned.

## 8. Open questions

1. Live confirmation of MPN, status, stock and price for IIS2ICLXTR, LSM6DSV16XTR and ADXL355BEZ-RL at DigiKey, Mouser, Newark and Arrow.
2. From the ST datasheet: IIS2ICLX zero-g offset row, typ and max tempco rows, supply current, sensitivity tolerance, whether sensitivity is the same across full-scale settings, and turn-on settling time.
3. From the ST datasheet: LSM6DSV16X accelerometer tempco row and noise density; gyro sensitivity tolerance (sets the flip-yaw accuracy).
4. ADXL355 lifecycle status direct from ADI, and its 1,000-piece price.
5. Pin tables of LSM6DSV16X, BMI270 and ICM-45686 for a shared footprint.
6. Real seating repeatability of a 42 mm, 25-35 g puck on bentgrass and bermuda at normal mowing heights: 30 placements for each base geometry on three greens against a long digital level.
7. Hard-surface reseating repeatability of the three-pad base on a cradle and on ordinary tables.
8. Thermal-gradient error in the assembled puck under a sun lamp and after a pocket-to-cold-plate transfer, for both the accelerometer and the camera boresight.
9. Whether 1 mrad (0.1% slope) is acceptable to the break model; if yes, whether the LSM6DSV16X alone meets it across temperature.
10. Not evaluated by either pass and possibly worth a look: Analog Devices ADXL380 / ADXL382 (small, thin, low-noise 3-axis parts from a US-HQ maker, by reviewer recollection). Offset tempco unknown. UNVERIFIED.
11. Freedom-to-operate review of US 10293236 and US 11980797, which the first report surfaced but could not read.
12. KX132-1211, ICM-42670-P, ADXL357 and MXC400x were not verified by either pass. None is expected to change the recommendation.

## 9. Sources

No URL was successfully opened in this verification pass (see section 0). The list below is the set of URLs cited by the first report. They are recorded so that a follow-up check can go straight to them. **None was re-opened or re-verified here.**

1. https://www.st.com/resource/en/datasheet/iis2iclx.pdf
2. https://www.st.com/en/mems-and-sensors/iis2iclx.html
3. https://www.st.com/resource/en/application_note/an5551-precise-and-accurate-tilt-sensing-in-industrial-applications-stmicroelectronics.pdf
4. https://www.st.com/resource/en/design_tip/dt0140-tilt-computation-using-accelerometer-data-for-inclinometer-applications-stmicroelectronics.pdf
5. https://estore.st.com/en/iis2iclxtr-cpn.html
6. https://octopart.com/part/stmicroelectronics/IIS2ICLXTR
7. https://se.rs-online.com/web/p/motion-sensor-ics/2049945
8. https://www.st.com/en/mems-and-sensors/iis3dhhc.html
9. https://www.st.com/resource/en/datasheet/iis3dhhc.pdf
10. https://www.st.com/resource/en/datasheet/lsm6dsv16x.pdf
11. https://www.st.com/en/mems-and-sensors/lsm6dsv16x.html
12. https://www.digikey.com/en/products/detail/stmicroelectronics/LSM6DSV16XTR/16841908
13. https://www.mouser.com/datasheet/2/389/lsm6dsv16x-3006807.pdf
14. https://www.analog.com/media/en/technical-documentation/data-sheets/adxl354_adxl355.pdf
15. https://www.mouser.com/datasheet/2/609/adxl354_adxl355-3122364.pdf
16. https://www.analog.com/en/products/adxl355.html
17. https://www.digikey.com/en/products/detail/analog-devices-inc/ADXL355BEZ-RL7/7100491
18. https://www.digikey.co.uk/en/products/detail/analog-devices-inc/ADXL355BEZ-RL/6490626
19. https://www.mouser.com/en/ProductDetail/Analog-Devices/ADXL355BEZ?qs=vcbl%2BK4rRld73tJrFMMu%2Fg%3D%3D
20. https://www.findchips.com/search/ADXL355
21. https://www.analog.com/en/resources/technical-articles/managing-stress-and-strain-to-get-the-best-perf-in-hi-prec-tilt-angle-sensing.html
22. https://ez.analog.com/mems/f/q-a/584140/stress-and-strain-from-conformal-coating-for-adxl355-and-tolerance-to-moisture
23. https://www.analog.com/en/products/ADXL354.html
24. https://www.analog.com:443/media/en/technical-documentation/data-sheets/adxl356-357.pdf
25. https://cdn.sparkfun.com/assets/2/e/1/8/6/adxl367.pdf
26. https://www.invensense.tdk.com/en-us/products/6-axis/icm-45686
27. https://invensense.tdk.com/products/motion-tracking/6-axis/icm-45686
28. https://www.digikey.com/en/products/detail/tdk-invensense/ICM-45686/24374985
29. https://www.mouser.com/en/ProductDetail/TDK-InvenSense/ICM-45686?qs=vvQtp7zwQdPk96IFOwypvQ%3D%3D
30. https://github.com/betaflight/betaflight/issues/14249
31. https://www.invensense.tdk.com/en-us/products/6-axis/icm-42688-p
32. https://product.tdk.com/system/files/dam/doc/product/sensor/mortion-inertial/imu/data_sheet/ds-000347-icm-42688-p-v1.6.pdf
33. https://www.digikey.com/en/products/detail/tdk-invensense/ICM-42688-P/10824934
34. https://cdn.sparkfun.com/assets/4/2/e/d/c/IIM-42652_Datasheet.pdf
35. https://www.digikey.fr/en/products/detail/tdk-invensense/IIM-42652/13901975
36. https://www.bosch-sensortec.com/products/motion-sensors/imus/bmi270/
37. https://www.digikey.com/en/products/detail/bosch-sensortec/BMI270/9974486
38. https://cdn.sparkfun.com/assets/5/c/0/0/d/bst-bmi270-ds000.pdf
39. https://www.bosch-sensortec.com/en/products/motion-sensors/imus/bmi323
40. https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi323-ds000.pdf
41. https://www.mouser.com/en/new/bosch/bosch-bmi323-imu/
42. https://www.bosch-sensortec.com/en/products/motion-sensors/accelerometers/bma456
43. https://cdn.sparkfun.com/assets/1/2/c/2/f/BMA456.pdf
44. https://www.bosch-sensortec.com/en/products/motion-sensors/accelerometers/bma580
45. https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bma580-ds000.pdf
46. https://www.mouser.com/new/bosch/bosch-bma580-accelerometers/
47. https://www.murata.com/~/media/webrenewal/products/sensor/pdf/datasheet/datasheet_scl3300-d01.ashx?la=en-us
48. https://www.newark.com/murata/scl3300-d01/inclinometer-90deg-digital/dp/01AH7953
49. https://www.digikey.it/en/products/detail/murata-electronics/SCL3300-D01-1/9950618
50. https://www.digikey.com/en/product-highlight/m/murata-electronics-north-america/scl3300-series-3-axis-inclinometer
51. https://www.farnell.com/datasheets/3773836.pdf
52. https://www.digikey.com/en/products/detail/murata-electronics/SCL3400-D01-1/17100254
53. https://www.futureelectronics.com/npi/murata-scl3400-inclinometer
54. https://www.newark.com/murata/scl3400-d01/inclinometer-90deg-digital/dp/58AK1231
55. https://www.st.com/resource/en/datasheet/iis3dwb.pdf
56. https://www.futureelectronics.com/ftm/motor-control/stmicroelectronics-iis3dwb-vibration-sensor
57. https://st.com/en/mems-and-sensors/lsm6dso32.html
58. https://st.com/en/mems-and-sensors/lsm6dso32x.html
59. https://fscdn.rohm.com/kionix/en/datasheet/kx134-1211-e.pdf
60. https://www.kionix.com/product/KX134-1211
61. https://www.rohm.com/products/sensors-mems/accelerometer-ics/kx134-1211-product
62. https://www.tti.com/content/ttiinc/en/apps/part-detail.html?partsNumber=KX134-1211&mfgShortname=ROH
63. https://www.digikey.com/en/products/detail/memsic-inc/MXC4005XC/10322569
64. https://www.alldatasheet.com/datasheet-pdf/pdf/1361272/MEMSIC/MXC4005XC.html
65. https://www.arrow.com/en/products/mxc4005xc/memsic
66. https://www.nxp.com/docs/en/data-sheet/FXLS8974CF.pdf
67. https://www.st.com/en/mems-and-sensors/fxls8974cf.html
68. https://www.mouser.com/new/nxp-semiconductors/nxp-fxls8974cf-digital-iot-accelerometer/
69. https://www.bosch-sensortec.com/en/products/motion-sensors/magnetometers/bmm350
70. https://www.digikey.com/en/products/detail/bosch-sensortec/BMM350/17827576
71. https://www.mouser.com/datasheet/2/783/Bosch_2_9_2023_BMM350-3103880.pdf
72. https://www.digikey.com/en/products/detail/memsic-inc/MMC5983MA/10452795
73. https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/333/MMC5983MA_RevA_4-3-19.pdf
74. https://www.trustedparts.com/en/part/memsic/MMC5983MA
75. https://breakmaster.com/breakmaster-gr01
76. http://www.practicerange.com/Golf-Training-Aids/Breakmaster-Putting-Green-Reader.aspx
77. https://performancebrandsaustralia.com.au/products/breakmaster-digital-green-reader
78. https://sites.google.com/view/greenslope/home
79. https://www.usga.org/content/usga/home-page/course-care/green-section-record/64/issue-13/location--location--location--choosing-good-spots-to-measure-gre.html
80. https://impactzonegolf.com/learn-read-putts-better-pro/

Local check script (arithmetic only, no network): the recomputation covered one-second noise averaging, tempco x temperature swing, the flip-calibration error formula, seating geometry, the root-sum-square budget, heading error, drift ratios, pad-seat sensitivity and thermal bow.
