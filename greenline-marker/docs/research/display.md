# GreenLine research: round sunlight-readable display for the aim line

Date: 2026-11-11

Document type: independent verification of an earlier research report on the display subsystem of the GreenLine electronic ball marker (reflective memory LCD or e-paper, cover window, drive requirements), plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web, and neither could the first report.

- Web search: four queries were attempted (LS013B7DH03 datasheet, LS013B7DH03 at DigiKey, LS010B7DH04 datasheet, LS012B7DD06 interface). All four were refused with "web search budget is used up" (a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.digikey.com`, `www.mouser.com`, `www.adafruit.com` and `www.sharpsde.com` failed to resolve (hosts outside this session's allowed network domains). No further hosts were tried, as the tool instructs.
- What could be reached: the session's network policy allows package registries. Five published open-source driver packages for these displays were downloaded with their normal package managers (pip, cargo, go) and their source code was read. These are secondary sources: they show what driver authors took from the datasheets and what works on real hardware. They are not the manufacturer's datasheet and say nothing about outline dimensions, price, stock or lifecycle.
- The locally installed KiCad 7.0.11 library was read for the three FPC connector footprints.
- All arithmetic and optics in the first report were recomputed with a local script.

Consequences:

- **No outline dimension, thickness, supply range, price, stock level or lifecycle status in this document was confirmed against a manufacturer or distributor source.** Every such item is marked UNVERIFIED and carries forward the first report's value, which was from model memory.
- What was confirmed from independent (secondary) sources: that the recommended and fallback part numbers exist as 128 x 128 Sharp memory LCDs, the 10-pin 0.5 mm FPC of the primary, the SPI protocol (chip select polarity, bit order, command bits, frame layout), an SPI clock limit, an EXTCOMIN frequency, the resolution table of the Sharp family, and the resolution and interface of one JDI alternative.
- Where the reviewer's own recollection of a datasheet (model training data, up to about mid-2026) agrees or disagrees with the report, that is stated as "reviewer recollection". Recollection is not a source, does not change an UNVERIFIED mark, and is not independent of the first report's memory-based values.
- The display bill of materials is therefore **not release-ready**. The display technology choice and the firmware protocol are on reasonably firm ground. The mechanical numbers and the sourcing are not.

Hosts that need to be allowed in the session network settings (or checked by a person) before design freeze: `www.digikey.com`, `www.mouser.com`, `www.arrow.com`, `www.newark.com`, `www.sharpsde.com`, `www.j-display.com`, `www.adafruit.com`, `www.azumotech.com`, `www.molex.com`, `www.hirose.com`, `www.te.com`, `www.edmundoptics.com`, `www.mcmaster.com`, `www.esslinger.com`, `abrisatechnologies.com`. Raising the web search limit (`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`) or a follow-up run would also allow the searches to be repeated.

## 1. Summary

The first report recommended a Sharp LS013B7DH03 (1.28 inch, 128 x 128, monochrome reflective memory LCD, SPI) behind a round aperture, with the Sharp LS010B7DH04 (about 1.0 inch, 128 x 128) as a fallback for a smaller puck, and rejected e-paper, round TFT and AMOLED. It stated openly that every part fact was from memory.

Nothing found in this pass contradicts that choice. The recommendation stands, as a provisional one. The review produced these confirmations, corrections and additions:

1. **Part existence and protocol are confirmed by independent driver sources.** Three separately written drivers treat the LS013B7DH03 as a 128 x 128 SPI memory LCD; one calls it 1.28 inch with a 10-pin 0.5 mm FPC. Two drivers list the LS010B7DH04 as 128 x 128. Chip select active high, least significant bit first, the three mode bits and the frame layout all match the first report.
2. **EXTCOMIN rate: the first report's doubt is justified, and the baseline should change.** The only driver written specifically for the LS013B7DH03 says to toggle EXTCOMIN at 65 Hz. Generic drivers say "at least once per second". Until the datasheet is read, plan a hardware 64 Hz square wave (32.768 kHz divided by 512) with EXTMODE high. 64 Hz lies inside the 54-65 Hz range the first report recalled. Treat 1 Hz as an optimisation that needs datasheet proof.
3. **SPI clock:** the same driver gives a maximum of 1.1 MHz. The report's design value of 1 MHz is fine.
4. **The 0.90 degree "angular step" is arithmetically right but overstates the limit.** It applies only if the line's end point is snapped to a whole pixel. A line rasterised from the real-valued angle carries its direction in the stair-step pattern along its whole length; the orientation error of a 128-pixel line is about 0.04 degrees rms. Display resolution does not limit aim accuracy. 128 pixels is sufficient.
5. **The quarter-wave film claim is wrong in one detail.** The report says the film costs "roughly half the light on each pass". It does not. Incoming sunlight is unpolarised and is unaffected. Without sunglasses the loss is only the film's few percent of surface and absorption loss. With polarised sunglasses the film replaces a brightness that varies from full to black with rotation by a constant one half. The report's second option (mount the panel at 45 degrees and accept dimming) does not work, because the angle between panel and viewer is not fixed.
6. **Sapphire is the wrong material for the display cover.** It is birefringent (noted in the enclosure research document), which interacts with the LCD polariser and polarised sunglasses, and it reflects 7.7% per face against 4.0% for glass. Use mineral glass for prototypes and strengthened glass for production. The first report marked the "sapphire or mineral watch crystal" option as recommended; keep only the mineral glass half.
7. **The puck diameter estimate leaves out the seal land.** The report's 43.3 mm is the glass bounding circle plus clearance plus wall. That is achievable only if the LCD sits under a ledge with an air gap to the cover (42.5 mm with 0.8 mm walls, 43.3 mm with 1.2 mm walls). An optically bonded full-face cover needs a continuous seal land outside the glass corners, which gives about 44.1-45.5 mm. The primary display does not fit the 42 mm working size used in the power research document. All of this rests on the unverified 26.6 x 30.3 mm outline.
8. **A 22.5 mm aperture is too tight.** It leaves 0.27 mm per side inside the 23.04 mm active area. Use 22.0 mm (0.52 mm per side) unless mask-to-panel alignment is held to about 0.2 mm.
9. **Two errors in rejected or secondary candidates.** The JDI LPM009M360A is a 0.85-0.9 inch part according to its driver, not 0.99 inch. The JDI LPM013M126 pixel pitch of 0.126 mm does not agree with a 1.28 inch diagonal at 176 pixels (that needs about 0.131 mm); the 0.126 mm figure fits the Sharp LS012B7DD06 instead.
10. **One conflict that stays open.** A published Rust driver lists the round 240 x 240 Sharp LS012B7DD06 as a supported model of the same SPI protocol, marked untested. The first report (and reviewer recollection) says this part uses a 6-bit parallel interface and two supply rails. Not resolved here. It does not change the recommendation, because no US stock is known for that part either way.

## 2. Final recommendation after review

Status: provisional. Part existence and firmware protocol confirmed from secondary sources. All dimensions, electrical limits, prices, stock and lifecycle UNVERIFIED. Amendments from this review are marked [A].

**Primary: Sharp LS013B7DH03.** 1.28 inch, 128 x 128, monochrome reflective memory LCD, write-only SPI, 10-pin 0.5 mm FPC. Reported (UNVERIFIED) 3.0 V single supply, glass outline 26.6 x 30.3 mm, thickness under 1.0 mm, active area 23.04 x 23.04 mm, -20 to +70 C. Shown through a round aperture printed on the cover glass.

**Fallback: Sharp LS010B7DH04.** 128 x 128, about 1.0 inch (reported active area about 18 x 18 mm), same protocol. Use it if the puck has to stay at or below 42 mm. Its outline is not known; the first report's 21 x 26 mm is a guess. Same manufacturer and family as the primary, so it is a size fallback, not a second source.

**Not to be designed in without a confirmed US channel:** JDI LPM013M126C (176 x 176, 8 colours, SPI; confirmed as a working SPI part by a driver, sourcing unknown) and JDI LPM010M297B (reported round 208 x 208; no source of any kind found).

**Rejected:** round 240 x 240 OEM parts (Sharp LS012B7DD06, JDI LPM012M134B), e-paper, round TFT, AMOLED. Reasons as in the first report; see the candidate table.

Mechanical and optical:

1. Orient the glass with its 30.3 mm axis fore-aft so the driver ledge and FPC fold sit at the rear. The four circular segments beside the glass are the only places where full-height parts can stand beside the display [A].
2. Aperture diameter 22.0 mm [A].
3. Cover: 1.0 mm mineral-glass watch crystal for prototypes; custom chemically strengthened glass disc with black printed mask for production. Not sapphire [A].
4. Quarter-wave retarder film at 45 degrees to the panel's polariser axis, between panel and cover. Required, not optional, if polarised sunglasses are in scope [A].
5. Decide between two cover constructions [A]:
   - Bonded (optically clear adhesive between cover and panel): thinnest stack, about 1.9-2.6 mm including film and foam; needs a puck of about 44-45.5 mm for a continuous seal land.
   - Air gap (panel installed from below under the cover ledge): puck 42.5-43.3 mm; stack about 3.1-3.3 mm; needs an anti-reflection coating on the inner cover face.
6. Support the panel on a flat rigid shelf with thin foam. The battery must not bear on it.

Firmware drive requirements (protocol items confirmed from driver sources; timing values UNVERIFIED):

1. Supply 3.0 V (reported range 2.7-3.3 V, UNVERIFIED). Hold all display inputs low while the supply is off.
2. SPI write-only, mode 0, chip select **active high**, least significant bit first, 1 MHz (maximum reported 1.1 MHz) [A].
3. Mode byte bits, in the order sent: M0 = write, M1 = VCOM, M2 = all clear. On a most-significant-bit-first bus these are 0x80, 0x40, 0x20 and the line address is bit-reversed.
4. Frame: mode byte; then per line: address (1 to 128), 16 data bytes (1 = white), 8 dummy bits; then 8 more dummy bits. A full frame is 2306 bytes, 18.4 ms at 1 MHz. Send only changed lines.
5. VCOM inversion: EXTMODE strapped high, EXTCOMIN driven by a hardware timer at 64 Hz from the 32.768 kHz clock [A]. Make the rate a build constant. Use 1 Hz only if the datasheet allows it.
6. Power-up and power-down sequence and all microsecond timings: take from the datasheet. The first report's values are from memory.
7. Draw the line from the real-valued angle, 5-7 pixels wide, across the full aperture, without snapping the end points to pixels [A]. Add the numeric aim offset as the first report proposed.

Before BOM freeze, a person or a session with network access must read the LS013B7DH03 and LS010B7DH04 datasheets and the live DigiKey and Mouser pages. Section 7 lists what to read off them.

## 3. Candidate table

"Confirmed (driver)" means confirmed from the open-source driver packages in section 8, not from a datasheet. Everything else in the table is the first report's value from memory and is UNVERIFIED.

| Name | MPN | Maker / HQ | Key specs | Dimensions (mm) | Interface / supply | Price (USD) | US distributors / stock | Lifecycle | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1.28 in square mono memory LCD | LS013B7DH03 | Sharp / Japan (parent Hon Hai, Taiwan; reviewer recollection) | 128 x 128, 1.28 in: confirmed (driver). Pitch 0.180, active 23.04 x 23.04 (self-consistent with 1.28 in), reflective, 12 uW static, -20 to +70 C: UNVERIFIED | Outline 26.6 x 30.3, thickness under 1.0: UNVERIFIED (reviewer recollection agrees on 26.6 x 30.3 and about 0.75 thick; not independent) | SPI, chip select active high, LSB first, max 1.1 MHz, EXTCOMIN 65 Hz, 10-pin 0.5 mm FPC: confirmed (driver). 3.0 V single rail: UNVERIFIED | 18-22 at 1: UNVERIFIED | DigiKey, Mouser reported; stock today UNVERIFIED | UNVERIFIED | Recommended (provisional) |
| 1.0 in square mono memory LCD | LS010B7DH04 | Sharp / Japan | 128 x 128: confirmed (driver). Active about 18 x 18: UNVERIFIED | Unknown. 21 x 26 is a guess | Same SPI protocol: confirmed (driver, untested by its author). 3.0 V, 10-pin FPC: UNVERIFIED | 13-17 at 1: UNVERIFIED | DigiKey, Mouser reported; UNVERIFIED | UNVERIFIED | Fallback (size) |
| 1.26 in 144 x 168 mono memory LCD | LS013B7DH05 | Sharp / Japan | 144 x 168: confirmed (driver). Usable circle 144 px | Unknown | Same SPI protocol: confirmed (driver) | 17-20; Adafruit breakout about 25: UNVERIFIED | Adafruit product 3502 is a 1.3 in 144 x 168 breakout: confirmed (Adafruit driver documentation). Stock UNVERIFIED | UNVERIFIED | Viable; bench prototype only |
| 1.19 in round 240 x 240 memory LCD | LS012B7DD06 | Sharp / Japan | 240 x 240: confirmed (driver constants). Round, 64 colours: UNVERIFIED | Unknown | Conflict: report says 6-bit parallel and two rails; one driver lists it as SPI, untested. UNVERIFIED | Unknown | No US stock known. UNVERIFIED | UNVERIFIED | Rejected (no channel; interface in doubt) |
| 1.39 in round 280 x 280 memory LCD | LS014B7DD01 | Sharp / Japan | All UNVERIFIED | Unknown; too large for the puck if active diameter is about 35 | UNVERIFIED | Unknown | UNVERIFIED | UNVERIFIED | Rejected |
| Sharp stripe and rectangular parts | LS012B7DD01; LS011B7DH03; LS018B7DH02 | Sharp / Japan | 184 x 38; 160 x 68; 230 x 303: confirmed (driver) | Unknown | SPI family | Unknown | UNVERIFIED | UNVERIFIED | Rejected (not usable for a 360 degree line or too large) |
| 1.28 in 176 x 176 8-colour reflective LCD | LPM013M126C (also LPM013M126A) | Japan Display Inc. / Japan | 176 x 176, 8 colours, "1.28 inch": confirmed (driver, tested by its author). Pitch: report's 0.126 is inconsistent; about 0.131 if 1.28 in [calc] | Unknown | SPI, chip select active high, 4-bit and 1-bit pixel modes: confirmed (driver). Supply UNVERIFIED | Unknown | No US distributor confirmed. Azumo lead UNVERIFIED | UNVERIFIED | Viable only with a confirmed US channel |
| 1.0 in round 208 x 208 reflective LCD | LPM010M297B | Japan Display Inc. / Japan | All UNVERIFIED. No driver found in the crates.io registry search | Unknown | UNVERIFIED | Unknown | UNVERIFIED | UNVERIFIED | Unverifiable; do not design in |
| 1.2 in round 240 x 240 reflective LCD | LPM012M134B | Japan Display Inc. / Japan | All UNVERIFIED | Unknown | Reported 6-bit parallel. UNVERIFIED | Unknown | UNVERIFIED | UNVERIFIED | Rejected |
| 72 x 144 strip reflective LCD | LPM009M360A | Japan Display Inc. / Japan | 72 x 144, 8 colours, 0.85-0.9 in: confirmed (driver). Report's "0.99 in" corrected | Unknown | SPI: confirmed (driver) | Unknown | UNVERIFIED | UNVERIFIED | Rejected (strip format) |
| E-paper 1.54 in square | Report cites GDEY0154D67 from memory (UNVERIFIED MPN) | Good Display / China; Pervasive Displays, E Ink / Taiwan | 1.54 in 200 x 200 e-paper panels exist: confirmed (driver for a sibling panel). 0-50 C, 1-2 s refresh: UNVERIFIED | Reported 31.8 x 37.3; bounding circle 49.0 [calc] | SPI plus control lines, 3.3 V. UNVERIFIED | Unknown | No small round e-paper known in US stock. UNVERIFIED | UNVERIFIED | Rejected |
| Round IPS TFT 1.28 in 240 x 240 | Generic GC9A01 panel | Various / China | Round GC9A01 SPI display, 240 x 240: confirmed (driver). Backlit, transmissive | Reported 35 x 38 x 1.6-2.3. UNVERIFIED | 4-wire SPI | Low | Breakout vendors. UNVERIFIED | UNVERIFIED | Rejected (not sunlight readable at low power) |
| Round AMOLED 1.2 in 390 x 390 | none | Various | All UNVERIFIED | Unknown | QSPI or MIPI | Unknown | UNVERIFIED | UNVERIFIED | Rejected |
| Kyocera memory LCDs | none | Kyocera / Japan | No data | Unknown | Unknown | Unknown | UNVERIFIED | UNVERIFIED | Not researched |
| Cover A: flat watch crystal 1.0 mm | by diameter | US watch-material houses (names from memory, UNVERIFIED) | Mineral glass: 4.0% reflection per face [calc]. Sapphire: 7.7% per face [calc], birefringent | Diameter to suit, 1.0 thick | n/a | Mineral 2-5, sapphire 10-25: UNVERIFIED | UNVERIFIED | n/a | Recommended for prototypes in mineral glass only [A] |
| Cover B: custom strengthened glass disc with printed mask | custom drawing | US glass fabricators (names from memory, UNVERIFIED) | Black mask gives the round aperture and hides the square panel | Diameter to suit, 0.7-1.0 thick | n/a | Quote | UNVERIFIED | n/a | Recommended for production |
| Cover C: laser-cut hard-coated acrylic | none | Sheet and cutting vendors (UNVERIFIED) | 3.9% reflection per face [calc]; scratches | 1.0-1.5 thick | n/a | Low | UNVERIFIED | n/a | Fallback, early prototypes only |
| FPC connector, 10-pos 0.5 mm, bottom contact | 54548-1071 | Molex / USA | "10 bottom-side contacts, 0.5mm pitch, 1.2mm height": confirmed (local KiCad footprint description) | Footprint body outline 10.2 x 4.55; height 1.2 (KiCad) | n/a | Unknown | UNVERIFIED | UNVERIFIED | Viable if the tail presents bottom contacts |
| FPC connector, 10-pos 0.5 mm | FH12-10S-0.5SH | Hirose / Japan | Footprint exists: confirmed (local KiCad). Bottom contact, 2.0 high: UNVERIFIED | Footprint body outline 8.1 x 5.6 (KiCad) | n/a | Unknown | UNVERIFIED | UNVERIFIED | Viable; taller |
| FPC connector, 10-pos 0.5 mm, top contact | 1-1734839-0 | TE Connectivity / Switzerland or Ireland (UNVERIFIED) | "10 top-side contacts, 0.5mm pitch, SMT": confirmed (local KiCad) | Footprint body outline 10.43 x 4.4 (KiCad); height not known | n/a | Unknown | UNVERIFIED | UNVERIFIED | Viable if the tail presents top contacts |

## 4. Key findings with confidence

1. **The LS013B7DH03 is a real 128 x 128, 1.28 inch SPI memory LCD with a 10-pin 0.5 mm FPC.** Three independent driver packages agree on the resolution; one states the size and FPC. Confidence: high for existence, resolution and interface; none for current availability. Sources 2, 3, 5.

2. **The Sharp SPI protocol in the first report is correct.** Chip select is active high in every driver read. Bits go least significant first (the Adafruit and both Rust drivers reverse the address byte; the TinyGo example sets LSB-first on the bus). Mode bits are write, VCOM and clear in that order. Each line is address, data, 8 trailing bits, with 8 more at the end. Full frame for 128 x 128: 1 + 128 x 18 + 1 = 2306 bytes = 18,448 clocks = 18.4 ms at 1 MHz. Confidence: high. Sources 1, 2, 4, 5.

3. **SPI clock limit for the primary is reported as 1.1 MHz.** The LS013B7DH03-specific driver says "MAX baudrate of 1.1 MHz". Generic examples for other family members use 2 MHz, which must not be copied for this part. SPI mode: the LS013B7DH03 driver and the TinyGo example use mode 0; one generic driver uses mode 1 for several other models, including the fallback LS010B7DH04 (untested by its author). Use mode 0 for the primary and confirm both parts on the datasheet timing diagrams. Confidence: medium (secondary source). Sources 1, 2, 4, 5.

4. **EXTCOMIN frequency is not settled, and the safer reading is about 60 Hz.** The LS013B7DH03 driver says 65 Hz. A second driver's notes say "use either 60Hz PWM or GND" (written mainly for JDI panels). Two others say at least once per second. This matches the first report's recollection of a 54-65 Hz datasheet line. A 64 Hz square wave from a 32.768 kHz timer satisfies the 65 Hz reading; the panel power figures at that rate are not known. Confidence: medium that the datasheet specifies roughly 54-65 Hz; low on the power consequence. Sources 2, 3, 4, 5.

5. **The Sharp family table in the first report is right, so several brief part numbers are not round.** LS010B7DH04 128 x 128; LS011B7DH03 160 x 68; LS012B7DD01 184 x 38; LS013B7DH03 128 x 128; LS013B7DH05 144 x 168; LS018B7DH02 230 x 303; LS027B7DH01 400 x 240; LS032B7DD02 336 x 536; LS044Q7DH01 320 x 240. Confidence: high. Source 5.

6. **No round reflective display with a confirmed simple interface and a US channel was found.** This pass found no evidence either way on US stock. The LS012B7DD06 interface is in conflict between the report and one untested driver entry. Confidence: low; the question is open. Source 4.

7. **Angular resolution is not a reason to want more pixels.** Step with snapped end points: 0.895 degrees at 128 px, 0.651 at 176, 0.551 at 208, 0.477 at 240 (report's arithmetic confirmed). With an un-snapped rasterised line the least-squares orientation error from pixel quantisation is about 0.04 degrees rms at 128 px. One degree at 3 m is 52 mm at the hole; the cup is 108 mm. The limit is the golfer's ability to extend a 22 mm line, as the first report says. Confidence: high (calculation).

8. **Quarter-wave film behaviour.** Without the film, a viewer in polarised sunglasses sees brightness proportional to the squared cosine of the angle between the panel's polariser and the glasses: full to zero. With the film at 45 degrees the output is circularly polarised and the glasses pass one half at any rotation. A viewer without sunglasses loses only the film's own few percent. The film is not achromatic, so expect a slight tint, which does not matter on a monochrome panel. A birefringent cover (sapphire, polycarbonate) above the film would partly undo it. Confidence: high (first-principles optics); film part and thickness not researched.

9. **Surface reflections.** Glass n = 1.50: 4.0% per face. Acrylic: 3.9%. Sapphire n = 1.768: 7.7% per face (report said about 7.5%). An air gap adds two glass-air faces behind the outer one. The panel's white reflectance of 17-20% is the first report's memory value, UNVERIFIED; if it is right, three uncoated faces reflect a specular 12% against a diffuse 17-20%, which is why bonding or an anti-reflection coating matters at glare angles. Confidence: high for the Fresnel numbers, low for the panel reflectance.

10. **Puck diameter with the primary display, recomputed.** Inputs UNVERIFIED (26.6 x 30.3 mm glass). Glass bounding circle 40.32 mm.
    - Panel under a ledge, air gap, 0.3 mm clearance: 42.5 mm with 0.8 mm walls; 43.3 mm with 1.2 mm walls (the report's figure).
    - Bonded full-face cover, continuous seal land outside the glass corners: 42.9 mm (1.0 mm land, cover edge exposed), 44.1 mm (1.0 mm land, 0.6 mm protective lip), 45.5 mm (1.5 mm land, 0.8 mm lip).
    - Concentric window: 46.2 mm if the driver ledge is 5.5 mm, as the report assumed. The result moves from 44.6 to 47.0 mm as the ledge goes from 4.5 to 6.0 mm, so it cannot be fixed without the outline drawing.
    - A 42 mm puck allows a glass bounding circle of only 39.0 mm with 1.2 mm walls, or 39.8 mm with 0.8 mm walls. The primary does not fit either way.
    Confidence: high for the arithmetic, low for the inputs.

11. **Display stack height.** Bonded: cover 0.7-1.0 + adhesive 0.1-0.2 + film 0.1 + panel 0.75-1.0 + foam 0.2-0.3 = 1.85-2.6 mm. Air gap under a 0.8 mm ledge: cover 1.0 + tape 0.2 + ledge 0.8 + panel 0.75-1.0 + foam 0.3 = 3.05-3.3 mm. The first report's 1.8-2.1 mm left out the film and the foam. Confidence: medium (reviewer estimate on unverified thicknesses).

12. **E-paper, TFT and AMOLED rejections.** The reasoning is sound, but its inputs (0-50 C, refresh time, outline, brightness, power) are UNVERIFIED. The existence of 1.54 inch 200 x 200 e-paper panels and of round 240 x 240 GC9A01 SPI displays is confirmed by drivers. Confidence: medium for the conclusion. Sources 6, 7.

13. **FPC connectors.** The three footprints exist in the local KiCad 7.0.11 library with the descriptions the first report quoted. Whether the display tail needs top or bottom contact, and the tail thickness, are not known. Distributor stock and lifecycle are UNVERIFIED. Confidence: high for the footprints, none for sourcing. Sources 8, 9, 10.

## 5. Verification table

Verdicts: confirmed, corrected, contradicted, unverifiable. "Secondary" means the evidence is an open-source driver package, not a datasheet or distributor page.

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | LS013B7DH03 exists; 128 x 128, 1.28 in, monochrome SPI memory LCD | confirmed (secondary) | - | Three independent drivers. Sources 2, 3, 5 |
| 2 | LS013B7DH03 has a 10-pin 0.5 mm FPC | confirmed (secondary) | - | Driver comment "10pin 0.5mm FPC". Source 3 |
| 3 | LS013B7DH03 outline 26.6 x 30.3 mm, thickness under 1.0 mm, pitch 0.180 mm, active 23.04 mm | unverifiable | - | Pitch and active area are self-consistent with 1.28 in. Reviewer recollection agrees on outline and about 0.75 mm thickness; not independent. Datasheet needed |
| 4 | LS013B7DH03 supply 3.0 V (2.7-3.3), 12 uW static, 50 uW at 1 Hz, -20 to +70 C | unverifiable | - | No source reached |
| 5 | LS013B7DH03 active, stocked at DigiKey and Mouser, 18-22 USD | unverifiable | - | Distributor hosts blocked. UNVERIFIED |
| 6 | LS010B7DH04 exists; 128 x 128, same SPI protocol | confirmed (secondary) | - | Listed in two drivers, neither tested on this model. Sources 4, 5 |
| 7 | LS010B7DH04 size, outline, supply, FPC, price, stock, lifecycle | unverifiable | - | Outline in the report is a guess. UNVERIFIED |
| 8 | SPI protocol: chip select active high, LSB first, mode bits M0/M1/M2, frame layout | confirmed (secondary) | - | Four drivers agree. Sources 1, 2, 4, 5 |
| 9 | SCLK at most 1 MHz | corrected (secondary) | Maximum 1.1 MHz reported; design at 1 MHz | Source 2. Do not copy the 2 MHz used in generic examples |
| 10 | SPI mode 0 | confirmed (secondary) for the primary | - | Mode 0 in the part-specific driver and the TinyGo example; one generic driver uses mode 1 for other models, including the LS010B7DH04. Check the timing diagrams. Sources 2, 4, 5 |
| 11 | Full frame 2306 bytes, 18.4 ms at 1 MHz | confirmed | - | Recomputed; framing matches the Adafruit driver. Source 1 |
| 12 | EXTCOMIN: datasheet may say 54-65 Hz although 1 Hz is common | corrected (secondary) | Baseline 64 Hz hardware square wave; 1 Hz only after datasheet check | Part-specific driver says 65 Hz. Sources 2, 3, 4, 5 |
| 13 | Power-up sequence and microsecond timing values | unverifiable | - | From memory in the report. Datasheet needed |
| 14 | Sharp family table; LS012B7DD01, LS011B7DH03, LS018B7DH02 are not round | confirmed (secondary) | - | Source 5 |
| 15 | LS012B7DD06 is 240 x 240 | confirmed (secondary) | - | Source 4 |
| 16 | LS012B7DD06 uses a 6-bit parallel interface and two rails and has no US stock | unverifiable | - | Conflict: source 4 lists it under an SPI driver, untested. Reviewer recollection sides with the report |
| 17 | Angular step 0.90 / 0.65 / 0.55 / 0.48 degrees | confirmed, interpretation corrected | 0.895 / 0.651 / 0.551 / 0.477 degrees for snapped end points; about 0.04 degrees rms for an un-snapped 128 px line | Display resolution does not limit aim accuracy |
| 18 | Puck diameter 43.3 mm off-centre, 46 mm concentric, 37 mm with the fallback | corrected | 42.5-43.3 mm air gap; 44.1-45.5 mm bonded with seal land; concentric 44.6-47.0 mm depending on ledge; fallback unknown | Arithmetic confirmed; seal land was missing; inputs UNVERIFIED |
| 19 | Display stack 1.8-2.1 mm | corrected | 1.85-2.6 mm bonded; 3.05-3.3 mm air gap | Film and foam were left out. Reviewer estimate |
| 20 | Quarter-wave film removes the sunglasses blackout "at the cost of roughly half the light on each pass" | corrected | No significant loss without sunglasses; constant one half with polarised sunglasses | The "panel at 45 degrees" alternative does not work |
| 21 | Sapphire watch crystal as a recommended display cover | corrected | Mineral or strengthened glass | Sapphire is birefringent and reflects 7.7% per face |
| 22 | Fresnel: about 4% per glass face, about 7.5% per sapphire face | confirmed | 4.0% and 7.7% | Calculation |
| 23 | Aperture about 22.5 mm | corrected | 22.0 mm | 22.5 leaves 0.27 mm per side |
| 24 | JDI LPM013M126A/C: 176 x 176, SPI, 8 colours | confirmed (secondary) | - | Source 3, tested by its author |
| 25 | JDI LPM013M126 pitch 0.126 mm, active 22.18 mm | corrected | About 0.131 mm and 23.0 mm if the diagonal is 1.28 in [calc] | 0.126 mm gives 1.235 in. Datasheet needed |
| 26 | JDI LPM009M360A is 0.99 in | corrected (secondary) | 0.85-0.9 in; 72 x 144 confirmed | Source 3 |
| 27 | JDI LPM010M297B round 208 x 208 SPI | unverifiable | - | No source; registry search found no driver |
| 28 | JDI and Azumo US channel | unverifiable | - | UNVERIFIED lead |
| 29 | E-paper: 0-50 C, 1-2 s refresh, 31.8 x 37.3 mm outline, no round part in US stock | unverifiable | - | 1.54 in 200 x 200 panels exist (source 7). Bounding circle 49.0 mm recomputed |
| 30 | Round GC9A01 TFT 240 x 240 SPI exists; brightness and power figures | confirmed (existence); unverifiable (figures) | - | Source 6 |
| 31 | Adafruit product 3502 is a 1.3 in 144 x 168 Sharp memory display breakout | confirmed | - | Adafruit's own driver documentation. Price and stock UNVERIFIED. Source 1 |
| 32 | KiCad 7.0.11 has footprints for Molex 54548-1071, Hirose FH12-10S-0.5SH, TE 1-1734839-0 | confirmed | Body outlines from the footprints: 10.2 x 4.55; 8.1 x 5.6; 10.43 x 4.4 mm | Sources 8, 9, 10 |
| 33 | Connector heights, contact side of the display tail, stock and lifecycle | unverifiable | - | Molex 1.2 mm height is in the footprint description; the rest is UNVERIFIED |
| 34 | Cover window vendors, stocked diameters and prices | unverifiable | - | UNVERIFIED |
| 35 | Panel white reflectance 17-20% | unverifiable | - | UNVERIFIED |

## 6. Risks

1. **Verification gap.** Outline, thickness, supply range, price, stock and lifecycle of both Sharp parts are unverified in two consecutive passes. A wrong outline changes the puck diameter directly.
2. **Diameter.** With the reported outline the primary needs 42.5-45.5 mm depending on cover construction. It does not fit a 42 mm puck. The fallback's outline is unknown.
3. **Thickness.** The stack is 1.85-3.3 mm of a 6.5-7 mm device, depending on construction. The bonded stack is about 1 mm thinner but about 2 mm wider.
4. **Single manufacturer.** Primary and fallback are both Sharp. No drop-in second source is known. Sharp's display business has been restructuring (reviewer recollection, UNVERIFIED); check for end-of-life or last-time-buy notices.
5. **EXTCOMIN.** If the datasheet requires 54-65 Hz, a 1 Hz design may flicker or degrade the panel over time; if it allows 1 Hz, a 64 Hz design wastes a little power. VCOM inversion must never stop while an image is shown.
6. **Polarised sunglasses.** Requires a quarter-wave film and an isotropic cover. Adds a lamination step and about 0.1 mm.
7. **Sealing against a rectangular panel.** A continuous land around a 26.6 x 30.3 mm rectangle inside a round puck is what drives the bonded design to 44-45.5 mm. A land that narrows to 0.5 mm at the glass corners is a leak path.
8. **Optical bonding.** Not every US contract assembler offers it. An air gap needs an anti-reflection coating instead.
9. **Mask alignment.** A printed round aperture must be aligned to the active area within the margin chosen (0.5 mm at 22.0 mm).
10. **Thin glass in a printed shell.** The panel needs a rigid flat support; printed parts flex and creep.
11. **Heat and ultraviolet.** A dark puck in sun may exceed 60 C. The 70 C limit is unverified. Polarisers degrade under ultraviolet; specify a UV-blocking cover or adhesive.
12. **No light.** A reflective panel without a front light is unreadable at dusk.
13. **FPC.** Contact side, tail thickness and bend radius are unknown; the connector choice cannot be made yet.
14. **Interface conflict on the round Sharp part.** If the LS012B7DD06 really were SPI and obtainable, the square-panel compromise would be worth revisiting. Current evidence does not support planning on it.

## 7. Open questions

1. LS013B7DH03 datasheet: outline length, width and thickness; position of the active area on the glass; ledge width; FPC exit side, contact side, tail thickness and minimum bend radius; supply range; SCLK maximum; chip-select timing; EXTCOMIN frequency range in both EXTMODE settings; power at the chosen EXTCOMIN rate; operating and storage temperature; polariser axis direction; reflectance and contrast.
2. The same list for the LS010B7DH04.
3. Live DigiKey and Mouser pages for both parts: lifecycle status, stock, price at 1, 100 and 1000, lead time, any product change notice.
4. Is the LS012B7DD06 interface SPI or 6-bit parallel, and does any US distributor carry it?
5. Does the JDI LPM010M297B exist as described, and is any JDI reflective panel sold through a US authorized channel (directly or in an Azumo module)?
6. Which cover construction: bonded with a 44-45.5 mm puck, or air gap with a 42.5-43.3 mm puck and a thicker stack?
7. Is an off-centre window acceptable, or must the puck grow for a concentric one?
8. Which quarter-wave film (maker, thickness, adhesive) and which US converter can laminate it?
9. Which exact cover glass: stocked crystal diameters for prototypes; a quote for a printed strengthened disc for production.
10. Can the chosen US contract manufacturer do the optical bonding, or is a bonded cover-plus-panel subassembly bought in?
11. Is dusk readability required? If so a front light has to be reconsidered.
12. Does the chosen microcontroller have a low-power timer output that can produce 64 Hz in its sleep mode without waking the core?

## 8. Sources

Sources opened in this session. Items 1-7 are package archives downloaded from their registries with pip, cargo or go and read locally; the registry page address is given for reference. Items 8-11 are local files.

1. Adafruit CircuitPython SharpMemoryDisplay driver, version 1.4.19, PyPI source archive (file `adafruit_sharpmemorydisplay.py`, `docs/index.rst`, `examples/`): https://pypi.org/project/adafruit-circuitpython-sharpmemorydisplay/1.4.19/
2. `ls013b7dh03` Rust driver crate, version 0.4.2 (file `src/lib.rs`: 128 x 128, SPI mode 0, "MAX baudrate of 1.1 MHz", "toggle the pin at 65 Hz"): https://crates.io/crates/ls013b7dh03/0.4.2
3. `memory-lcd-spi` Rust driver crate, version 0.0.7 (files `README.md`, `src/displays.rs`, `src/lib.rs`: Sharp and JDI models, "LS013B7DH03 ... 10pin 0.5mm FPC", EXTCOMIN note): https://crates.io/crates/memory-lcd-spi/0.0.7
4. `sharp-memory-display` Rust driver crate, version 0.3.0 (files `README.md`, `src/lib.rs`, `src/ls012b7dd06.rs`, `src/ls010b7dh04.rs`): https://crates.io/crates/sharp-memory-display/0.3.0
5. TinyGo drivers Go module, version 0.37.0, package `sharpmem` (file `sharpmem/sharpmem.go`: model table, VCOM note; `examples/sharpmem`): https://pkg.go.dev/tinygo.org/x/drivers@v0.37.0/sharpmem
6. TinyGo drivers Go module, version 0.37.0, package `gc9a01` (round 240 x 240 SPI display driver): https://pkg.go.dev/tinygo.org/x/drivers@v0.37.0/gc9a01
7. TinyGo drivers Go module, version 0.37.0, package `gdew0154m09` (1.54 inch 200 x 200 e-paper driver): https://pkg.go.dev/tinygo.org/x/drivers@v0.37.0/gdew0154m09
8. Local KiCad 7.0.11 footprint: file:///usr/share/kicad/footprints/Connector_FFC-FPC.pretty/Molex_54548-1071_1x10-1MP_P0.5mm_Horizontal.kicad_mod
9. Local KiCad 7.0.11 footprint: file:///usr/share/kicad/footprints/Connector_FFC-FPC.pretty/Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal.kicad_mod
10. Local KiCad 7.0.11 footprint: file:///usr/share/kicad/footprints/Connector_FFC-FPC.pretty/TE_1-1734839-0_1x10-1MP_P0.5mm_Horizontal.kicad_mod
11. Enclosure research document in this repository (sapphire birefringence, wall and seal-land assumptions): `greenline-marker/docs/research/enclosure-manufacturing.md`

Addresses referenced inside the sources above but NOT opened in this session (blocked or not attempted). They are listed so a later pass can open them; nothing in this document relies on their content.

12. https://www.adafruit.com/product/3502 (blocked)
13. https://www.adafruit.com/product/1393
14. https://www.sharpsde.com/products/displays/memory-lcd/ (host blocked)
15. https://www.sharpsde.com/fileadmin/products/Displays/2016_SDE_App_Note_for_Memory_LCD_programming_V1.3.pdf
16. https://www.molex.com/pdm_docs/sd/545481071_sd.pdf
17. https://www.hirose.com/product/en/products/FH12/FH12-24S-0.5SH(55)/
18. https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Customer+Drawing%7F1734839%7FC%7Fpdf%7FEnglish%7FENG_CD_1734839_C_C_1734839.pdf%7F4-1734839-0
19. https://github.com/BogdanOlar/ls013b7dh03
20. https://github.com/andelf/memory-lcd-spi
21. https://git.sr.ht/~doesnotcompete/sharp-memory-display
22. https://github.com/adafruit/Adafruit_CircuitPython_SharpMemoryDisplay
23. https://www.digikey.com/ and https://www.mouser.com/ product pages for LS013B7DH03 and LS010B7DH04 (hosts blocked)
