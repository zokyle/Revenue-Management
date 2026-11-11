# GreenLine research: micro camera modules for the forward stereo pair

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web.

- Web search: four queries were attempted and all four were refused ("web search budget is used up", a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.ovt.com`, `www.digikey.com` and `www.omnivision-group.com` all failed to resolve (hosts outside this session's allowed network domains). No further hosts were tried, as the tool instructs.

Consequences:

- **No part number, dimension, price, stock level or lifecycle status in this document was confirmed against a live source in this pass.** Every such item is marked UNVERIFIED. The values are carried forward from the first report, and that report itself took them from search-result extracts, not from opened datasheets or live distributor pages.
- What was verified here: every calculation in the first report (recomputed with a local script), the internal consistency of its quoted optical data, and the engineering logic. Two minor numeric corrections and several additions came out of that (sections 5 and 6).
- Where the reviewer's own recollection (model training data, up to about mid-2026) agrees or disagrees with the report, it is labelled "reviewer recollection". Recollection is not a source and does not lift an UNVERIFIED mark.

Before any layout or purchase, a person or a follow-up session with network access must open the OmniVision product brief and full datasheet for the OVM7692 and the live DigiKey pages for OVM7692-RYAA, OVM7692-RAAA and OVM9724-RADA. Hosts that need to be allowed in the session's network settings: `www.ovt.com`, `www.omnivision-group.com`, `www.digikey.com`, `mm.digikey.com`, `www.mouser.com`, `www.arrow.com`, `www.findchips.com`, `octopart.com`, `www.himax.com.tw`, `www.sparkfun.com`, `cdn.sparkfun.com`, `www.analog.com`, `github.com`, `www.usga.org`, `www.randa.org`.

## 1. Summary

The first report concluded that the only lens-included cameras small enough to stand on edge inside a 6-7 mm puck, and listed by a US distributor, are OmniVision reflowable CameraCubeChip parts. It recommended the OVM7692-RYAA (VGA) as primary and the OVM9724-RADA (720p) as fallback, and it reported an honest negative: a 34 mm stereo baseline is marginal for ranging beyond about 5 m.

Result of this review:

1. Nothing was found that contradicts the recommendation, but nothing about part existence, stock, price, lifecycle or package size could be confirmed against a source. The recommendation is therefore provisional.
2. All of the report's arithmetic is correct to rounding (focal length in pixels, disparity, range error per 0.1 px, flagstick width in pixels, yaw-stability requirement, frame sizes).
3. The quoted optical data are internally consistent. For the OVM7692, EFL 1.15 mm and image area 1148 x 861 um give a diagonal field of 63.9 degrees against the quoted 64. For the OVM9724, EFL 1.6 mm with 1280 x 720 pixels of 1.4 um gives 65.4 degrees against the quoted 65. Three independently quoted numbers agreeing this closely makes a transcription error in any one of them unlikely. It does not prove the part numbers or stock status.
4. The stereo concept is weaker than the first report states. Calibrating the pair against "far background at zero disparity" biases the range long by a factor of 1 / (1 - z / Z_background), whatever camera is used. With a tree line at 100 m that is +5% at 5 m and +11% at 10 m. With one at 50 m it is +11% and +25%.
5. The first report's remedy, monocular known-size ranging, has limits it did not state. The flagstick top is outside the frame at short range, flagstick height is not standardised, and from a lens 4 mm above the turf the cup itself cannot be seen at all, so the flagstick must be in the hole.
6. The OVM9724 is a performance upgrade that needs a different capture interface and a 3,000-piece buy. It is not a supply fallback. The supply fallback is the sibling SKU OVM7692-RAAA.

## 2. Final recommendation

Status: provisional. Not confirmed against live sources in this pass (section 0).

Parts:

- **Primary: two OmniVision OVM7692-RYAA CameraCubeChip modules**, reflowed on edge so the optical axis is horizontal, read out over the 8-bit DVP parallel port, one camera at a time. Reported data: 640 x 480 colour, 1.75 um pixel, EFL 1.15 mm, F/3.0, 64 degrees diagonal, package 2.95 x 3.47 x 2.76 mm (2.76 mm along the optical axis), DigiKey 884-1027-1-ND, Active, roughly 1.8-2.5k in stock, $27.50 at 1 and $6.25 at 2,500. All UNVERIFIED.
- **Supply fallback (same sensor and lens): OVM7692-RAAA**, reported 2.815 x 3.179 x 2.6 mm, black coating instead of metal can, reported 1,230 in stock at DigiKey. Lay out the keep-out for the larger RYAA outline. Whether the two SKUs share one ball pattern is UNVERIFIED and must be read from the datasheet.
- **Performance upgrade, not a drop-in: OVM9724-RADA** (never the -R1 suffix). Reported 1280 x 720, 1.4 um, EFL 1.6 mm, F/2.8, 3.9 x 2.9 x 2.4 mm, MIPI CSI-2 one lane only, DigiKey non-stock with 3,000 minimum at about $4.57 and 14 weeks lead, lifecycle flags conflicting. It needs an MCU with a CSI-2 receiver and a different footprint (reported 28 balls against 25). Choose it only if field trials show the OVM7692 cannot detect the flagstick at the required distance. All UNVERIFIED.
- **Second-vendor stopgap with reduced function: Himax HM01B0-MNA-00FT870** FPC module. Reported 5.0 mm lens holder and EFL 0.66 mm. It would make the puck about 7.5-8 mm thick and cannot support stereo ranging (0.62 px disparity at 10 m). All UNVERIFIED.
- **Worth one enquiry: OmniVision OCH2B30.** Reported 1500 x 1500 pixels in a 2.565 x 2.565 mm footprint, but built for dental scanning with a 140 degree lens at F/5.5. Ask OmniVision for the focus distance and price before ruling it in or out. UNVERIFIED.

System-level amendments that follow from the numbers in sections 5 and 6:

1. Do not use far background as a zero-disparity reference by itself. Use a factory stereo calibration held by a rigid common datum for both cameras, and use the smallest background disparity seen in each read only as a bound on calibration drift. Sky and cloud texture, or terrain beyond about 1 km, is a valid zero reference. A tree line at 50-300 m is not.
2. State the stereo range performance honestly: about 2% at 5 m and 4.5% at 10 m per 0.1 px of disparity error on the OVM7692, before any calibration bias.
3. Provide a distance input that does not depend on stereo: manual entry in paces or feet on the device or over BLE, and optionally a per-course learned flagstick height (measured by stereo on a putt of about 4-6 m, then reused monocularly on longer putts).
4. Require the flagstick to be in the hole and the ball to be lifted during a read. The device cannot see the cup from 4 mm above the turf, and a ball left in front of the marker blocks both cameras.
5. Decide camera orientation deliberately. With the optical axis horizontal, half of the vertical field looks at turf within about 11 mm of the lens. Portrait orientation, an upward tilt of 10-15 degrees, or both, would put more of the flagstick in frame. An upward tilt of 15 degrees adds about 0.7 mm to the camera bay height (reviewer estimate).
6. Reconcile the mounting with the inertial-sensor document in this folder, which asks for cameras and accelerometer on one rigid board. Two separate folded flex tabs do not provide the 5 um relative stability that 0.1 px needs. Each cube needs a hard locating datum on a common rigid member.
7. Before layout, buy 10-20 pieces and run an outdoor trial at 3, 5 and 10 m. Reviewer recollection, UNVERIFIED: the Analog Devices MAX78000FTHR board carries an OVM7692 on its DVP interface and the ADI MSDK includes a driver, which would make that board a ready-made capture rig.

## 3. Candidates

All catalogue values in this table are carried forward from the first report and are UNVERIFIED in this pass. Items marked [calc] were recomputed here from those values. Maker headquarters are reviewer recollection.

| Name | MPN | Maker / HQ | Key specs | Dimensions (mm) | Interface / supply | Price (USD) | US distributors / stock | Lifecycle | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| OVM7692 CameraCubeChip, VGA colour, metal can | OVM7692-RYAA | OmniVision Technologies / Santa Clara, CA, USA; parent company is Chinese (reviewer recollection: Will Semiconductor, Shanghai, since renamed OmniVision Group) | 640 x 480, 1.75 um, 1/13 inch, EFL 1.15 mm, F/3.0, 64 deg diagonal; f = 657 px [calc]; 51.9 x 40.1 deg over 640 x 480 [calc]; 120 mW active, 23 uA standby | 2.95 x 3.47 x 2.76 (2.76 along optical axis), 25-ball CSP, no flex | 8-bit DVP parallel or MIPI serial, SCCB control; single 2.8 V with internal 1.5 V core regulator | 27.50 at 1; 6.25 at 2,500 | DigiKey 884-1027-1-ND, 1,814-2,497 in stock by snapshot, 14 weeks lead; no Mouser listing found | Active at DigiKey; design dates from about 2010 | Recommended (provisional) |
| OVM7692 CameraCubeChip, VGA colour, black coating | OVM7692-RAAA | OmniVision / USA | Same sensor and lens as RYAA | 2.815 x 3.179 x 2.6 | As RYAA | 5.625 at 2,500 (Arrow) | DigiKey 1,230 in stock; Arrow out of stock, 26 weeks lead | Active | Supply fallback |
| OVM9724 CameraCubeChip, 720p | OVM9724-RADA | OmniVision / USA | 1280 x 720, 1.4 um, EFL 1.6 mm (one listing 1.66), F/2.8, 65 deg diagonal; f = 1143 px [calc]; 58.5 x 35.0 deg [calc]; -30 to +70 C | 3.9 x 2.9 x 2.4 (older releases say 2.3 or 2.5 high), 28-ball CSP | MIPI CSI-2, 1 clock + 1 data lane, 400 Mbps; SCCB; 1.5 V core, 2.8 V analogue, 1.8 V I/O; no parallel output | 4.57 at 3,000; no small-quantity price seen | DigiKey non-stock, 3,000 minimum, 14 weeks lead | Conflicting: Active on DigiKey US page, "Discontinued at DigiKey" on DigiKey MX page | Upgrade option, not a drop-in fallback |
| Himax HM01B0 QVGA module, mono, 87 deg lens, FPC | HM01B0-MNA-00FT870 | Himax Technologies / Tainan, Taiwan | 324 x 324 array (320 x 320 effective), 3.6 um, under 4 mW at QVGA 60 fps; lens data from the -01FT870 variant datasheet: EFL 0.66 mm, F/2.4, 87 x 87 deg; f = 183 px [calc] | Holder 5.0 x 5.0; overall 20.0 x 12.5, height 3.39; 24-pin 0.5 mm FPC tail | DVP 8/4/1-bit plus I2C; 1.5-2.8 V rails | 12.33 at 1 | DigiKey 832 in stock | Active at DigiKey; datasheet marked Preliminary | Second-vendor stopgap; too thick and too wide-angle for stereo |
| Himax HM0360 VGA module, mono, 96 deg lens, FPC | HM0360-MWA-00FP963 | Himax / Taiwan | 640 x 480, 3.6 um; f about 360 px if 96 deg is diagonal [calc] | Not retrieved | DVP plus I2C | Not retrieved | DigiKey listing exists; stock not seen | Unknown | Viable on paper; data missing |
| OVM7690 CameraCubeChip, VGA | OVM7690-R20A | OmniVision / USA | 640 x 480, 1.75 um; lens data not retrieved | 2.5 x 2.9 x 2.5 | Not retrieved | 2.96-9.85 at third-party sellers | DigiKey 884-1019-1-ND, Active, 16 weeks lead, stock not seen | Conflicting: DigiKey Active, Octopart Obsolete | Viable only if stock is confirmed |
| OCH2B30 CameraCubeChip, 2 MP square, dental | OCH2B30-RAUA-001A | OmniVision / USA | 1500 x 1500, 1.12 um, 140 deg diagonal, F/5.5; focus distance not published | 2.565 x 2.565 x 3.634, 24-pin | MIPI plus SCCB; 2.8 V and 1.2 V | Not found | DigiKey non-stock, 8 weeks lead | Current (2024 product) | Enquire; likely close-focus |
| OC0TB CameraCubeChip, 400 x 400 global shutter | OC0TB1B-RAWH-001A | OmniVision / USA | 400 x 400 mono, 2.2 um, 95 or 120 deg; f about 260 px at 95 deg [calc] | Not retrieved | MIPI 1-lane or SPI | Not found | DigiKey non-stock, 8 weeks lead | Current | Rejected: focal length in pixels too low |
| OVM7251 / OVM6211 global-shutter cubes | OVM7251-RAIA and others | OmniVision / USA | 640 x 480 or 400 x 400 mono, 3 um, NIR lens variants | Not retrieved | MIPI | Not found | No DigiKey or Mouser listing found | Listed by maker | Rejected: no US distributor found |
| OVM6946 / OVM6948 medical cameras | OVM6946-RAJA-1B; OVM6948-RALA | OmniVision / USA | Sub-millimetre endoscope cameras, 400 x 400 and 200 x 200 (reviewer recollection) | Not retrieved | Analogue output (reviewer recollection) | 63.25 at 512 (OVM6946) | DigiKey non-stock, 24 weeks lead; OVM6948 discontinued at DigiKey | Poor | Rejected |
| Sony IU233 ultra-small module | IU233N2-Z; IU233N5-Z | Sony Semiconductor Solutions / Japan | 1296 x 816, F2.4, 80.7 deg | 2.6 x 3.3 x 2.32 | MIPI 1-lane | Not found | None found | Obsolete | Rejected |
| ams OSRAM NanEyeC / NanEyeM | NEC_B&W_SGA_FOV120_F4.0 and others | ams OSRAM / Austria and Germany | 320 x 320, 120 deg | About 1 x 1 footprint | Bit-serial | 87.65 at 1 (NanEyeM) | Mouser obsolete; DigiKey discontinued or 9 in stock | Obsolete | Rejected |
| ams OSRAM Mira050 / Mira016 | Sensor boards only | ams OSRAM / Austria and Germany | Bare global-shutter sensors and evaluation boards | No lens module | - | 69.91 (board) | DigiKey non-stock | Mixed | Rejected: needs custom optics |
| ST VD55G1 camera modules | CAM-5G1-160CLR; CAM-5G1-081CLR (order-code spelling differs from the family name CAM-55G1; check) | STMicroelectronics / Switzerland | Global shutter, 81-179 deg lens options | 6.5 square head | FPC | 18.82 at 1 | DigiKey 48 in stock | Active | Rejected: 6.5 mm head |
| PixArt PAJ6100U6 reflowable QVGA | PAJ6100U6 | PixArt Imaging / Taiwan | 320 x 240 global shutter, 3.0 um, 90 deg; f about 200 px [calc]; 1.4 mW | 4.1 x 3.9 x 2.1 | 8-bit parallel plus SPI control | Not found | No DigiKey or Mouser listing found | Listed by maker | Rejected: resolution and US sourcing |
| SparkFun Red Vision Camera Board, HM01B0 colour | SEN-29468 | SparkFun Electronics / USA | HM01B0 on a breakout | Larger than the limit | 3.3 V, headers | 54.95 | SparkFun, Mouser | Active; SEN-15570 retired | Rejected: bring-up tool only |
| Adafruit Ultra Tiny USB camera; OV5640 breakouts | Adafruit 5733; 5838 / 5840 / 5841 | Adafruit / USA | USB VGA webcam; 5 MP breakouts | 8 x 25 x 4.5; 35.7 x 23.0 x 17.5 | USB; DVP | 6.95; 9.95-17.50 | Adafruit, Mouser, Newark | Active | Rejected: size and interface |
| OV9734 endoscope modules | None | Chinese module houses | 1280 x 720, close focus | 3.2-3.9 diameter | USB or MIPI | Not found | None found | Unknown | Rejected: sourcing and focus |

## 4. Key findings, with confidence

Confidence here reflects what this pass could establish. "High" is used only for results that were recomputed.

1. **The OVM7692 CameraCubeChip is the best-fitting part on the evidence available.** Confidence: medium that the part and its optical data are as described (the EFL, image area and field of view agree with each other to 0.1 degree, and reviewer recollection is that the OVM7692 is a real VGA cube used on a current Analog Devices board). Confidence: low on today's stock, price and lifecycle (UNVERIFIED).
2. **Focal length in pixels: OVM7692 657, OVM9724 1143, HM01B0 module 183.** Confidence: high for the arithmetic, medium for the inputs.
3. **Stereo range error per 0.1 px of disparity error, 34 mm baseline:** OVM7692 0.040 / 0.112 / 0.448 m at 3 / 5 / 10 m (1.3 / 2.2 / 4.5 %); OVM9724 0.023 / 0.064 / 0.257 m; HM01B0 0.144 / 0.401 / 1.604 m. Confidence: high for the arithmetic.
4. **A background-referenced stereo calibration is biased, independent of the camera.** If scenery at distance Z_b is treated as infinitely far, the measured range is 1 / (1/z - 1/Z_b). See the table in section 6. Confidence: high (geometry).
5. **Holding 0.1 px between the cameras means 152 urad of relative yaw, or 5.2 um of differential movement across 34 mm, for the OVM7692.** For the OVM9724 the figures are 87.5 urad and 3.0 um. A printed enclosure will not hold this. Confidence: high for the arithmetic.
6. **A 12.7-19 mm flagstick at 10 m is 0.83-1.25 px wide on the OVM7692, 1.45-2.17 px on the OVM9724, 0.23-0.35 px on the HM01B0.** Confidence: high for the arithmetic. The flagstick diameters are reviewer recollection of the equipment rules (lower section not more than 19 mm), UNVERIFIED.
7. **Diffraction already spreads a point over about 2.3 px on the OVM7692 (Airy diameter 4.0 um at F/3.0, 550 nm) and 2.7 px on the OVM9724 (3.8 um at F/2.8).** The OVM9724's angular resolution advantage is therefore about 1.5 times, not the 1.74 times that pixel count alone suggests. Confidence: medium (reviewer calculation from the reported F-numbers; real lens performance not measured).
8. **Focus is unlikely to be a problem for the standard variants.** Hyperfocal distance for a 2-pixel blur is about 0.13 m for the OVM7692 and 0.33 m for the OVM9724, so any fixed focus beyond that keeps infinity sharp. Confidence: medium (reviewer calculation). The close-focus -R1 medical variant of the OVM9724 remains unsuitable.
9. **The cameras do not set puck thickness if the reported package sizes are right.** A cube with its 2.95 mm side vertical needs a bay of about 3.6-4.1 mm. Confidence: low to medium (engineering estimate resting on unverified dimensions, unknown ball pitch and unknown image orientation).
10. **The Himax FPC modules are stocked but unsuitable for stereo.** Confidence: medium for the conclusion (the 183 px focal length is decisive even if the holder size is off), low for stock and price.
11. **The OVM9724 is MIPI-only.** Reviewer recollection is that few BLE-capable microcontrollers have a CSI-2 receiver, so this choice would probably force a two-chip architecture. Confidence: medium.

## 5. Verification table

Verdicts: confirmed (recomputed or matched to a source), corrected, contradicted, unverifiable (no source reachable in this pass).

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | OVM7692-RYAA exists, is Active and is purchasable at DigiKey today | Unverifiable | - | No distributor page reachable. Reviewer recollection: the OVM7692 CameraCubeChip is a real part and an OVM7692 is fitted to the Analog Devices MAX78000FTHR. Check sources 2 and 3. |
| 2 | OVM7692-RYAA stock 1,814-2,497, $27.50 at 1, $6.25 at 2,500, 14 weeks lead | Unverifiable | - | The first report's own snapshots disagree by 683 pieces. Treat as indicative only. |
| 3 | OVM7692-RYAA package 2.95 x 3.47 x 2.76 mm, 25-ball CSP | Unverifiable | - | From the product brief as surfaced in search extracts. Ball pitch, ball map and which edge is parallel to the image rows are not known. |
| 4 | OVM7692 optics: 1.75 um, image area 1148 x 861 um, EFL 1.15 mm, F/3.0, 64 deg diagonal | Unverifiable against source; internally consistent | - | Recomputed diagonal field from EFL and image area is 63.9 deg. |
| 5 | OVM7692 field "about 53 x 41 deg" | Corrected | 51.9 x 40.1 deg over the 640 x 480 output; 53.0 x 41.0 deg applies to the full 1148 x 861 um image area (656 x 492 px) | Minor. Paraxial, no distortion. |
| 6 | OVM7692 RYCA / RACA variants: EFL 1.10 mm with 71.9 deg diagonal | Unverifiable; internally inconsistent | Paraxial value from the same image area is 66.2 deg | Either the 71.9 deg figure includes distortion or one number is wrong. Not decision-critical because RYAA / RAAA are the chosen SKUs. |
| 7 | OVM7692 interface and power: DVP or MIPI plus SCCB, single 2.8 V with internal 1.5 V regulator, 120 mW active, 23 uA standby | Unverifiable | - | Reviewer recollection agrees on DVP and SCCB, and that the SCCB address is fixed (0x3C, 7-bit), so two cameras need two buses or a multiplexer. |
| 8 | OVM9724-RADA: DigiKey non-stock, 3,000 minimum, $4.57, 14 weeks lead, conflicting lifecycle | Unverifiable | - | Check sources 8, 9 and 11. Ask OmniVision directly for lifecycle. |
| 9 | OVM9724 package 3.9 x 2.9 x 2.4 mm; EFL 1.6 mm; F/2.8; 65 deg; MIPI 1-lane 400 Mbps; 1.5 / 2.8 / 1.8 V | Unverifiable against source; internally consistent | - | 1.6 mm with 1280 x 720 at 1.4 um gives 65.4 deg diagonal. The alternative 1.66 mm gives 63.5 deg, so 1.6 mm fits the quoted 65 deg better. 720p30 RAW10 is 276 Mbps before blanking, consistent with a 400 Mbps lane. |
| 10 | OVM9724 classed as "fallback" at "the same thickness" | Corrected | Performance upgrade, not a drop-in fallback | Different footprint, MIPI CSI-2 only, 3,000-piece minimum, uncertain lifecycle. The supply fallback is OVM7692-RAAA. |
| 11 | Focal length in pixels: 657 / 1143 / 183 | Confirmed (arithmetic) | 657.1 / 1142.9 / 183.3 | Inputs are the unverified EFL and pixel sizes. |
| 12 | OVM7692 disparity 7.4 / 4.5 / 2.2 px and error 0.04 / 0.11 / 0.45 m per 0.1 px at 3 / 5 / 10 m | Confirmed (arithmetic) | 7.45 / 4.47 / 2.23 px; 0.040 / 0.112 / 0.448 m | - |
| 13 | OVM9724 error 0.023 / 0.064 / 0.26 m; HM01B0 0.14 / 0.40 / 1.6 m | Confirmed (arithmetic) | 0.023 / 0.064 / 0.257 m; 0.144 / 0.401 / 1.604 m | - |
| 14 | Flagstick 12.7-19 mm at 10 m is 1.3-1.9 mrad, 0.8-1.25 px (OVM7692), 1.5-2.2 px (OVM9724), 0.23-0.35 px (HM01B0) | Confirmed (arithmetic) | - | Diameters are reviewer recollection of the equipment rules, UNVERIFIED. |
| 15 | Background at 100 m shows 0.22 px on the OVM7692, "not a true zero-disparity reference" | Confirmed, and understated | Range bias +3.1 / +5.3 / +11.1 % at 3 / 5 / 10 m for a 100 m background | The bias is camera-independent. See section 6. |
| 16 | "Stereo alone is adequate only to roughly 5 m" | Confirmed as a judgment, with a condition | - | True for random error of 0.1 px (2.2% at 5 m). It also requires a calibration that does not rely on a near background. |
| 17 | 0.1 px is about 150 urad of relative yaw, about 5 um across 34 mm | Confirmed (arithmetic) | 152 urad, 5.2 um | - |
| 18 | Remedy: fuse with monocular known-size ranging (flagstick height, flag, cup) | Corrected | Usable only for the flagstick, only when its top is in frame, and only with a known height | Top of a 2.13 m stick is out of frame closer than 5.8 m (OVM7692, landscape, axis horizontal) or 4.4 m (portrait). Height is not standardised. The cup is not visible from 4 mm lens height. See section 6. |
| 19 | Camera bay 3.6-4.1 mm, puck 6-7 mm achievable | Unverifiable | - | Reasonable estimate if item 3 holds. A 25-ball CSP on a folded flex tab may need 75 um traces or via-in-pad; pitch unknown. |
| 20 | HM01B0-MNA-00FT870: 5.0 x 5.0 mm holder, EFL 0.66 mm, 87 x 87 deg, 832 in stock, $12.33 | Unverifiable | - | Lens data come from the -01FT870 variant datasheet and may not apply to -00FT870. Paraxial field from 0.66 mm and 320 x 3.6 um is 82 deg, so the quoted 87 deg implies about 8% barrel distortion at the edge of the field. The 12.5 mm width matches a 24-pin 0.5 mm FPC. |
| 21 | VGA frame 307 kB RAW8, 614 kB YUV422 | Confirmed (arithmetic) | 307,200 and 614,400 bytes | - |
| 22 | OmniVision is US-headquartered with a Chinese parent | Unverifiable | - | Reviewer recollection agrees: Santa Clara, California; owned since 2019 by Will Semiconductor of Shanghai, later renamed OmniVision Group. |
| 23 | SparkFun SEN-15570 retired; successor SEN-29468 at $54.95 | Unverifiable | - | Not decision-critical. |
| 24 | Estimated focal lengths: HM0360 about 360 px, OC0TB about 260 px, PAJ6100U6 about 200 px | Confirmed (arithmetic) | 360 / 259 / 200 | Rest on unverified field-of-view figures. |

## 6. Recomputed performance and additional physics

Inputs are the first report's unverified datasheet values. Baseline 34 mm. All fields are paraxial.

| Quantity | OVM7692 | OVM9724 | HM01B0 module |
|---|---|---|---|
| Focal length (px) | 657.1 | 1142.9 | 183.3 |
| Angle per pixel (mrad) | 1.522 | 0.875 | 5.455 |
| Slope per pixel (% grade) | 0.152 | 0.087 | 0.545 |
| Field over active array, H x V (deg) | 51.9 x 40.1 | 58.5 x 35.0 | 82.2 x 82.2 |
| Disparity at 3 / 5 / 10 m (px) | 7.45 / 4.47 / 2.23 | 12.95 / 7.77 / 3.89 | 2.08 / 1.25 / 0.62 |
| Range error per 0.1 px at 3 / 5 / 10 m (m) | 0.040 / 0.112 / 0.448 | 0.023 / 0.064 / 0.257 | 0.144 / 0.401 / 1.604 |
| Same, as % of range | 1.3 / 2.2 / 4.5 | 0.8 / 1.3 / 2.6 | 4.8 / 8.0 / 16.0 |
| Range error per 0.1 px at 15 m (m) | 1.01 | 0.58 | 3.61 |
| Flagstick 12.7-19 mm at 10 m (px) | 0.83-1.25 | 1.45-2.17 | 0.23-0.35 |
| Disparity of scenery at 100 m / 300 m / 1 km (px) | 0.223 / 0.074 / 0.022 | 0.389 / 0.130 / 0.039 | 0.062 / 0.021 / 0.006 |
| 0.1 px as relative yaw / as movement across 34 mm | 152 urad / 5.2 um | 87.5 urad / 3.0 um | 545 urad / 18.5 um |
| Airy disc diameter at 550 nm | 4.0 um = 2.3 px | 3.8 um = 2.7 px | 3.2 um = 0.9 px |
| Hyperfocal distance for 2 px blur | 0.13 m | 0.33 m | 0.03 m |
| 2.13 m flagstick fully in frame beyond, axis horizontal (landscape / portrait) | 5.8 m / 4.4 m | 6.8 m / 3.8 m | 2.4 m |
| 2.13 m flagstick height at 10 m (px) | 140 | 243 | 39 |

Range bias when scenery at distance Z_b is used as the zero-disparity reference. The same for every camera and baseline.

| True range | Z_b = 50 m | Z_b = 100 m | Z_b = 300 m | Z_b = 1 km |
|---|---|---|---|---|
| 3 m | +6.4% | +3.1% | +1.0% | +0.3% |
| 5 m | +11.1% | +5.3% | +1.7% | +0.5% |
| 10 m | +25.0% | +11.1% | +3.4% | +1.0% |

Additional points from this review (reviewer derivations, not from sources):

- **The cup cannot be seen.** From a lens 4 mm above the turf, the line of sight to a point 10 m away meets the ground at 0.4 mrad, and at 3 m at 1.3 mrad. A 108 mm hole is foreshortened to 0.04 mm at 10 m and 0.14 mm at 3 m, far below one pixel. The only detectable target is the flagstick, so the flagstick must be in the hole. Many golfers putt with it removed.
- **The base of the flagstick is partly hidden.** At these grazing angles any crown in the green or unevenness in the turf between marker and hole hides the bottom of the stick. A 20 mm crown hides 2 mrad at 10 m, which is 1.3 px on the OVM7692 and reads as 0.2% of extra uphill slope. The "elevation of the flagstick base" is really the elevation of its lowest visible point.
- **Half the field is spent on turf.** With the axis horizontal, the lower 20 degrees of the OVM7692 field meets the ground within 11 mm of the lens.
- **Monocular ranging and stereo are complementary.** Stereo is accurate where the flagstick top is out of frame (short putts). Flagstick height in pixels is accurate where stereo is weak: at 10 m a 1 px error in a 140 px stick is 0.7%. The missing piece is the stick's true height. It could be learned once per course from a mid-range read where both methods work, but only in portrait orientation or with an upward tilt, because in landscape the top first enters the frame at 5.8 m. Flagstick height is not fixed by the rules (reviewer recollection: a minimum of about 7 ft is recommended), so a stored default would be wrong on some courses.
- **Slope resolution is adequate.** One OVM7692 pixel is 0.15% grade. Locating a horizon or stick feature to 0.3 px gives about 0.05% grade, comparable to the 0.2-0.5 mrad gravity reference target.

## 7. Risks

1. Nothing about availability is confirmed. OVM7692 stock, price and Active status are search-result snapshots from the first report, and this pass added no confirmation.
2. The OVM7692 is a design from about 2010. End-of-life could come with little notice. A written longevity statement from OmniVision and a lifetime-buy plan are needed.
3. Single-vendor exposure. Primary, supply fallback and upgrade are all OmniVision parts, and OmniVision has a Chinese parent. The only second-vendor part (Himax) costs about 1.5 mm of thickness and loses the stereo function.
4. Stereo calibration. The 5 um stability requirement cannot be met by a printed enclosure or by two independent flex tabs, and background self-calibration is biased by 3-25% at 10 m depending on what is behind the green.
5. Flagstick dependence. No flagstick in the hole means no bearing, no range and no mean-slope reading from the cameras.
6. Detection margin. The flagstick is about one pixel wide at 10 m on the OVM7692 and narrower than the diffraction blur. Detection will depend on integrating along its length and on its contrast against the background, which was not tested.
7. Unknown package details. Ball pitch, ball map, I/O voltage range, MIPI lane count, tri-state behaviour and image orientation for the OVM7692 were not retrieved by either pass. A 25-ball CSP on a flex tab may need fine-line or via-in-pad fabrication, which raises cost at a US rigid-flex fabricator.
8. Two OVM7692 cameras share one SCCB address (reviewer recollection, UNVERIFIED), and a VGA frame needs 0.3-0.6 MB of buffer, both of which constrain the microcontroller.
9. Prototype cost. The reported single-piece price is $27.50, more than four times the reel price.
10. Sunlight. A lens a few millimetres above the grass will often have the sun or strong sky glare in frame. Flare and blooming behaviour of these phone-class cubes was not checked.
11. Mis-order risk. OVM9724-RADA-R1 is reported to be a close-focus medical variant with a part number one suffix away from the general-purpose part.
12. Sealing. Each camera needs a flat window for IP67. A window tilted or wedged by even a small amount shifts the image differently in the two cameras and must be included in the factory calibration.

## 8. Open questions

1. Are OVM7692-RYAA and OVM7692-RAAA Active and in stock at DigiKey today, at what price breaks, and is there any product change or end-of-life notice?
2. OVM7692 full datasheet: ball map and pitch, MIPI lane count, I/O voltage range, SCCB address, output tri-state in power-down (needed to share one DVP bus between two cameras), focus distance, distortion, and which package edge is parallel to the image rows.
3. Do RYAA and RAAA share one ball pattern, so that either can be placed on the same pads?
4. Is OVM9724-RADA still in production, what is its real lead time, and what is the focus distance of the non-R1 lens?
5. OCH2B30: focus distance, price, and whether OmniVision sells it to non-medical customers.
6. HM01B0-MNA-00FT870 versus -01FT870: do they share the 5.0 mm holder and 0.66 mm lens? HM0360-MWA-00FP963: head dimensions, EFL, stock and price.
7. Does the Analog Devices MAX78000FTHR carry an OVM7692 as recalled, and is that board still sold?
8. Can both cameras be located against one rigid member, and can the factory calibration then hold 0.1-0.2 px over temperature and handling? This needs a test on prototypes.
9. Is portrait orientation or an upward tilt acceptable to the mechanical design, and what does it cost in bay height?
10. Is a manual distance entry acceptable to the project as the fallback when stereo confidence is low or the flagstick is out?
11. What flagstick diameters and heights are in use on typical US courses? The rule limits quoted here are from memory.
12. Not searched by either pass: OV01A10 / OV02C10 narrow-bezel laptop modules, ST VD56G3 modules, and the Leopard Imaging, e-con Systems and TechNexion catalogues.

## 9. Sources

No URL below was opened in this verification pass. Sources 1-74 are the URLs cited by the first report, carried forward so that a follow-up pass can open them. The four URLs attempted here and refused by the network are sources 1, 2 and 7, plus the DigiKey page listed as source 75.

1. https://www.omnivision-group.com/files/pd/file/OVM7692-PB-v1.8-WEB.pdf
2. https://www.ovt.com/products/ovm7692/
3. https://digikey.com/product-detail/en/omnivision-technologies-inc/OVM7692-RYAA/884-1027-1-ND/3190559
4. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RAAA/3190565
5. https://www.arrow.com/en/products/ovm7692-raaa/omnivision-technologies.html
6. https://www.findchips.com/search/ovm7692
7. https://www.ovt.com/products/ovm9724/
8. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM9724-RADA/4377196
9. https://www.digikey.com.mx/en/products/detail/omnivision-technologies-inc/OVM9724-RADA/4377196
10. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM9724-RADA-R1/7321735
11. https://www.findchips.com/search/OVM9724-RADA
12. https://www.arrow.com/en/products/ovm9724-rada/omnivision-technologies.html?region=nac
13. https://cdn.sparkfun.com/assets/7/f/c/8/3/HM01B0-MNA-Datasheet.pdf
14. https://www.digikey.com/en/products/detail/himax/HM01B0-MNA-00FT870/14109821
15. https://www.bitcraze.io/documentation/hardware/ai_deck_mono_camera/ai_deck_mono_camera-datasheet.pdf
16. https://www.robotshop.com/products/bitcraze-ai-deck-monochrome-camera-module
17. https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/4886/HM01B0-MNA-00FT870.pdf
18. https://github.com/ArmDeveloperEcosystem/hm01b0-library-for-pico
19. https://www.sparkfun.com/himax-cmos-imaging-camera-hm01b0-monochrome.html
20. https://www.sparkfun.com/sparkfun-red-vision-camera-board-hm01b0-color.html
21. https://news.sparkfun.com/15354
22. https://github.com/sparkfun/SparkFun_Red_Vision_Camera_Board_HM01B0
23. https://www.digikey.ca/en/products/detail/himax/HM01B0-MWA/14109818
24. https://www.digikey.com/en/products/detail/himax/HM0360-MWA/14109823
25. https://www.digikey.com/en/products/detail/himax/HM0360-AWA/14109822
26. https://www.digikey.fr/en/products/detail/himax/HM0360-MWA-00FP963/14109819
27. https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/4287/HM0360-MWA-00FP963.pdf
28. https://www.arducam.com/product/arducam-hm0360-vga-spi-camera-module-for-raspberry-pi-pico-2/
29. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7690-R20A/2123272
30. https://octopart.com/part/omnivision-technologies/OVM7690-R20A
31. https://www.digikey.com/en/products/detail/microchip-technology/AC164150/3911101
32. https://www.ovt.com/wp-content/uploads/2024/06/OCH2B30-PB-v1.0-WEB.pdf
33. https://www.ovt.com/products/och2b30/
34. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OCH2B30-RAUA-001A/25322804
35. https://www.ovt.com/products/oc0tb/
36. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OC0TB1B-RAWH-001A/25322759
37. https://www.ovt.com/wp-content/uploads/2023/02/OG0TB-PB-v1.1-WEB.pdf
38. https://www.ovt.com/products/ovm7251/
39. https://www.ovt.com/wp-content/uploads/2024/08/OVM7251-PB-v1.4-WEB.pdf
40. https://octopart.com/part/omnivision-technologies/OVM7251-RAIA
41. https://www.ovt.com/products/ovm6211/
42. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM6946-RAJA-1B/6111516
43. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM6948-RALA/9452043
44. https://www.ovt.com/products/ochta10/
45. https://www.chip1stop.com/USA/en/view/dispDetail/DispDetail?partId=SONY-0004277
46. https://octopart.com/iu233n2-z-sony-78615953
47. https://cameota.com/sony/17286.html
48. https://www.mouser.com/ProductDetail/ams-OSRAM/NEC_BW_SGA_FOV120_F4.0?qs=DRkmTr78QAQ25p7zn0a0Rw%3D%3D
49. https://www.digikey.com/en/products/detail/ams-osram-usa-inc/NANEYE-CAMERA-MODULE-ME-1-M-2X2-RGB/15902898
50. https://www.digikey.com/en/products/detail/ams-osram-usa-inc/NEM-RGB-2M-FOV120-F4-0-FT-SE/15902908
51. https://ams-osram.com/products/sensor-solutions/cmos-image-sensors/ams-naneyec-integrated-camera-module
52. https://www.digikey.com/en/products/detail/ams-osram-usa-inc/MIRA050-MINI-SENSOR-BOARD-MONO/21700259
53. https://www.digikey.com/en/products/detail/ams-osram-usa-inc/MIRA016-MONO-SHIFTED-MINI-SB/28535784
54. https://ams-osram.com/products/sensor-solutions/cmos-image-sensors/ams-mira016-cmos-image-sensor
55. https://www.st.com/en/evaluation-tools/cam-55g1.html
56. https://www.digikey.com/en/products/detail/stmicroelectronics/CAM-5G1-160CLR/24738494
57. https://estore.st.com/en/cam-5g1-081clr-cpn.html
58. https://www.st.com/en/imaging-and-photonics-solutions/vd55g1.html
59. https://www.pixart.com/products-detail/107/PAJ6100U6
60. https://www.pixart.com/products-comparison/32/QVGA___VGA
61. https://www.epsglobal.com/products/semiconductors/sensing-and-haptics/cmos-image-sensors/pag7920lt
62. https://www.gophotonics.com/products/cmos-image-sensors/pixart/21-120-pag7920lt
63. https://www.adafruit.com/product/5733
64. https://www.newark.com/adafruit/5733/ultra-tiny-usb-camera-with-gc0307/dp/82AK1092
65. https://www.adafruit.com/product/5840
66. https://www.adafruit.com/product/5841
67. https://www.visionmeta.com/product/1mp-1-9inch-ov9734-720p-endoscope-%CF%863-5mm-hd-medical/
68. https://dothecamera.com/product/3-5mm-720p-1mp-endoscopic-camera-module-usb/
69. https://cdn.sparkfun.com/assets/b/3/e/8/e/HM01B0-MNA-Datasheet.pdf
70. https://community.sparkfun.com/t/confusing-schematic-connection-on-sparkfun-edge/64809
71. https://www.sparkfun.com/fpc-camera-connector-24-pin-0-5mm-bottom-contact.html
72. https://docs.openmv.io/v5.0.0/openmvcam/quickref/arduino-giga-r1-wifi.html
73. https://docs.arducam.com/Arduino-SPI-camera/Legacy-SPI-camera/Pico/Camera-Module/Arducam-HM01B0-QVGA-Camera-Module/
74. https://thepihut.com/collections/pico/products/vga-camera-module-for-raspberry-pi-pico-hm0360
75. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RYAA/3190559 (attempted in this pass; host not reachable)
