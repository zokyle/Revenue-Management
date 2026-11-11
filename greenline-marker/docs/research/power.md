# GreenLine research: battery, charging and power architecture

Date: 2026-11-11

Document type: independent verification of an earlier research report on the power subsystem of the GreenLine electronic ball marker (sealed puck, about dia 42 x 6.5 mm), plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web.

- Web search: four queries were attempted (PowerStream GM201030, BQ25100YFPR at DigiKey, SparkFun PRT-13852, TPS7A02). All four were refused with "web search budget is used up" (a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.powerstream.com`, `www.ti.com` and `www.sparkfun.com` failed to resolve. The session's cloud environment allows only package registries and a short list of unrelated hosts. No further hosts were tried, as the tool instructs.

Consequences:

- **No part number, dimension, price, stock level or lifecycle status in this document was confirmed against a live source in this pass.** Every such item is marked UNVERIFIED. They carry forward the first report's values. The first report took the cell, BQ25100 and 16 CFR 1263 data from search-result summaries (pages were not opened) and everything else from memory.
- What was verified here: all of the first report's arithmetic (recomputed with a local script), its internal consistency, and its engineering logic. That produced the corrections listed in sections 1 and 5.
- Where the reviewer's own recollection of a datasheet (model training data, up to about mid-2026) agrees or disagrees with the report, that is stated as "reviewer recollection". Recollection is not a source and does not change an UNVERIFIED mark. It is also not independent of the first report's "from memory" values, because both come from the same kind of model memory.
- The power bill of materials is therefore **not release-ready**. The architecture is settled; the parts are not confirmed.

Hosts that need to be allowed in the session network settings (or checked by a person) before design freeze: `www.powerstream.com`, `www.ti.com`, `www.digikey.com`, `www.mouser.com`, `www.sparkfun.com`, `www.arrow.com`, `www.mill-max.com`, `www.analog.com`, `www.nordicsemi.com`, `www.microchip.com`, `www.ecfr.gov`, `www.cpsc.gov`. Raising the web search limit (`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`) or a follow-up run would also allow the searches to be repeated.

## 1. Summary

The first report's architecture survives every check that could be made without the web: a sealed, non-user-replaceable lithium polymer pouch cell of 40-45 mAh, a small linear charger, inductor-free LDO rails, a resistor divider in place of a fuel gauge, and charging through flush contact pads in a cradle. Its energy-budget arithmetic is correct to rounding. Nothing was found that contradicts the architecture.

Corrections and additions from this review:

1. **Standby current is under-counted if the puck wakes on motion.** The report's off-state figure (3.5-6.5 uA) leaves out any wake source. A sealed puck has no button, so something must stay powered. If the IMU's wake-on-motion mode stays on between rounds at the report's own 3-10 uA, off-state drain becomes 6.5-16.5 uA (4.7-12.0 mAh per month), and "10 rounds in 10 weeks" becomes 19.8 mAh nominal / 59.5 mAh worst case. The worst case then exceeds the 43 mAh cell. The wake source must be defined and budgeted at 1 uA or less (a nano-power wake accelerometer, a Hall switch with a cradle magnet, or cradle-only wake).
2. **Battery-life statements need adjusting.** With the report's own inputs, a new cell (41 mAh usable) gives 9.4 worst-case rounds in 10 weeks and 6.8 at end of life (33 mAh), not "8-10". Nominal use is far better than stated: about 36-48 rounds in 10 weeks, or 7-12 months idle. The "3 months" figure only appears in the worst case with a wake sensor left on.
3. **A ship-mode PMIC does not stop the cell's own protection circuit from draining it.** About 3 uA of the off-state figure is the protection IC inside the battery pack, which sits on the cell side of any ship-mode switch. At 3 uA that is 26 mAh per year, 61% of the cell. Shelf life is set mainly by the protection IC's quiescent current, which is unknown for the PowerStream pack.
4. **The contact-pad description is ambiguous and, read literally, wrong.** For a 180 degree rotation to keep polarity, pads opposite each other must share a net: V at 0 and 180 degrees, G at 90 and 270 degrees (alternating V-G-V-G around the circle). "V,V,G,G" in sequence around the circle would reverse polarity at 180 degrees.
5. **The proposed input protection chain is inconsistent** (reviewer recollection of the parts, UNVERIFIED). The LM66100 ideal diode is a 5.5 V part, so it cancels the charger's 30 V input tolerance and sits behind a TVS that clamps well above 6 V during an ESD strike. A single low-profile Schottky diode rated 30 V or more is simpler, thinner, and keeps headroom: 5.0 V - 0.3 V = 4.7 V, and 4.75 V - 0.3 V = 4.45 V, against the charger's reported 4.45 V minimum.
6. **The 2 x 4.7 Mohm battery divider is sensitive to ADC input leakage.** Its source impedance is 2.35 Mohm. Each 10 nA of leakage shifts the reading by 47 mV at the battery, which is a large state-of-charge error on the flat part of the discharge curve. Use a lower-value or switched divider, or the BLE SoC's internal supply-measurement channel if the module is powered directly from the cell.
7. **"+1 mm thickness" for the 3.0 mm fallback cell is not established.** If the cell sits in a cut-out in the main board, it uses the same mid-layer height that the side-lying camera modules already require. Whether the penalty is 0 or +1 mm is a layout decision. The 20 mm long cell also fits beside a central grain sensor, which the 30 mm long cell cannot do (geometry in finding 4).
8. **GM201030's 43 mAh looks high against its sibling.** It implies about 265 Wh/L, versus 194 Wh/L for the GM201021 at the same thickness and width, and 224 Wh/L for the thicker SparkFun cell. Scaling GM201021 by active length suggests about 34 mAh. Confirm capacity from the datasheet and by measurement before relying on 43 mAh.
9. **Compliance items the report did not list** (reviewer recollection, UNVERIFIED): US DOE battery-charger energy conservation standards (10 CFR 430.32(z)) and California Energy Commission battery-charger rules apply to consumer products with rechargeable batteries; California SB 1215 adds a recycling fee and manufacturer notification duties for products with non-removable batteries from 2026; retailers commonly ask for IEC 62133-2 or UL 2054 on the battery and a UN 38.3 test summary.

## 2. Final recommendation

Status: architecture re-checked and kept. All part data UNVERIFIED in this pass. Amendments from this review are marked [A].

Architecture: sealed, non-user-replaceable LiPo pouch cell -> linear charger -> inductor-free LDO rails; charge through flush gold pads in a pogo-pin cradle.

Puck power bill of materials:

1. **Cell.** Carry two cells into mechanical layout and decide there [A]:
   - PowerStream GM201030-PCB: 3.7 V, reported 43 mAh, reported 2 x 10 x 30 mm plus protection board (overall length not known, assume 33-34 mm), reported $12.00 at quantity 1. Single source. Too long to sit beside a central base sensor in a 42 mm puck; it has to be stacked above or below the centre. UNVERIFIED.
   - SparkFun PRT-13852 (cell reported as Data Power DTP301120): 3.7 V, 40 mAh, reported 20 x 11 x 3.0 mm with protection circuit, reported $7.14 at quantity 1, reported DigiKey 1568-13852-ND. Fits beside a central sensor. Needs a 3.3-3.4 mm high bay, which is available only in a board cut-out. UNVERIFIED.
   - Size the bay for swelling and tolerance: nominal thickness + 0.4 mm [A] (the report's +0.3 mm is tight for a cell with a +0.2 mm thickness tolerance and up to 10% swell).
   - Ask the cell vendor for the protection IC's quiescent current and require 2 uA or less, or buy the bare cell and put a low-quiescent protection circuit on the main board [A].
2. **Charger.** TI BQ25100YFPR, reported 1.60 x 0.90 mm DSBGA. ISET 6.19 kohm for 21.8 mA (0.5C) if K_ISET is 135 A.ohm; termination about 10% (2.2 mA); 10 kohm NTC on TS, thermally coupled to the cell. Charge time about 2.5-3 h. UNVERIFIED. If a battery-voltage ADC, power path or ship mode is wanted, evaluate TI BQ25155 or BQ25180 in its place [A] (both from reviewer recollection, UNVERIFIED).
3. **Input protection.** TVS on the V pad (TI TPD1E10B06DPYR or equivalent); **one Schottky diode, 30 V or higher, low profile, in series** in place of the LM66100 [A]; 100 kohm pull-down on the V pad; 1 uF 25 V input capacitor.
4. **Rails.** TI TPS7A02 3.0 V always-on for the BLE module, memory LCD and IMU. A switched 2.8 V LDO for camera AVDD; because this rail is off between reads, quiescent current does not matter and a low-noise LDO is the better choice [A]. 1.8 V only if camera I/O needs it. LEDs from VBAT. All part codes UNVERIFIED. If the chosen BLE module accepts the cell directly on a high-voltage supply pin, the main LDO can be deleted (MCU topic).
5. **Battery sense.** Divider into the MCU ADC, no gauge IC. Use 2 x 1 Mohm (2.1 uA) or a switched divider, with the 100 nF reservoir capacitor, unless the ADC input leakage is confirmed below about 1 nA [A]. Read immediately before a measurement, at rest.
6. **Contacts.** Four flush pads at 90 degree spacing, **alternating V-G-V-G** [A], hard gold over nickel or solid plated studs, potted. Two steel keepers in the puck, magnets in the cradle.
7. **Wake source [A].** Define it and hold it to 1 uA or less. Do not leave a 3-10 uA IMU wake mode running between rounds.

Cradle: four spring pins (Mill-Max 0906-series reported, UNVERIFIED), two magnets, USB-C receptacle with two 5.1 kohm CC resistors, current-limited 5 V switch that enables only when a puck is detected [A].

Energy budget (first report's inputs, arithmetic confirmed here; nominal | worst):

- Per read: 0.0111 mAh (0.15 J) | 0.0393 mAh (0.54 J)
- Per 4.5 h round: 0.69 mAh | 2.98 mAh (reads are about 80%)
- Off state without a wake sensor: 2.6-4.7 mAh per month; with a 3-10 uA wake-on-motion IMU left on: 4.7-12.0 mAh per month [A]
- 10 rounds including 10 weeks standby: 14.7 mAh | 42.7 mAh; with the wake IMU left on: 19.8 mAh | 59.5 mAh [A]
- 43 mAh cell: about 41 mAh usable new, about 33 mAh at 80% end of life (estimates)

Expected life per charge with a 1 uA-class wake source [A]: nominal use is limited by calendar time, not rounds (about 36-48 rounds in 10 weeks; 7-12 months idle). Worst case is 9 rounds new and 7 at end of life in a 10-week window. If the vision pipeline needs an application-class processor (about 300 mW for 6 s), a read costs 0.13-0.17 mAh, life falls to about 4 rounds, and the 100 mA peak is 2.3C on a 43 mAh cell, which the cell may not be rated for.

Fallbacks: cell as above; charger or PMIC with ship mode (TI BQ25120A, BQ25180, BQ25155, Nordic nPM1300 / nPM1304), all UNVERIFIED. Do not use a coin cell of any chemistry: none fits the height, and all bring 16 CFR 1263 / UL 4200A obligations.

Before release: open the datasheet and a live US distributor page for every part above (exact order code, package height, price, stock, lifecycle); obtain from PowerStream the cell datasheet, protection-board outline and IC, maximum discharge current, UN 38.3 test summary, IEC 62133-2 status and a production quote; measure cell capacity and impedance at 5 C and 25 C.

## 3. Candidate table

All specification, price, stock and lifecycle entries are the first report's values. None was re-confirmed against a live source in this pass: treat every cell of this table as UNVERIFIED. "Reviewer recollection" records whether the reviewer's memory agrees; it is not a source. Source numbers refer to section 8 (URLs cited by the first report, not opened in this pass).

| # | Name | MPN | Maker / HQ | Key specs (first report) | Dimensions, mm | Interface / supply | Price | US distributors / stock | Lifecycle | Reviewer recollection | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | PowerStream thin LiPo with protection circuit | GM201030-PCB (bare: GM201030) | Cell: GM Battery / China. Seller: PowerStream / USA (Utah) | 3.7 V, 43 mAh, protection circuit, bare cell tagged UN38.3. Max discharge, protection thresholds and IC, IEC 62133 status not seen | 2 x 10 x 30 bare cell (T x W x L). Length with protection board not seen | Two leads or tabs; 3.0-4.2 V | $12.00 at 1 with protection; $10.00 bare (listing age unknown) | PowerStream web store only. Stock not confirmed. Not seen at DigiKey or Mouser | Listed; currency unknown | PowerStream is a US battery seller in Orem, Utah. The 201030 size code is a standard thin-cell size; 40-45 mAh is the range usually quoted for it. No recollection of this exact listing, its price or stock. Capacity looks high against GM201021 (see finding 3) | Recommended as the thin option, one of two cells to carry into layout. UNVERIFIED [S1-S4] |
| 2 | PowerStream thin LiPo, UL1642 | GM201021 | GM Battery / China; PowerStream / USA | 3.7 V, 22 mAh, "TUV UL1642 cert." | 2.0 x 10 x 21 | Tabs or leads; 3.0-4.2 V | $13.00 | PowerStream web store; stock not confirmed | Listed; currency unknown | No specific recollection | Viable. UNVERIFIED [S1] |
| 3 | PowerStream 20 mAh square cell | not shown in the search result | GM Battery / China; PowerStream / USA | 3.7 V, 20 mAh | 2 x 15 x 15 | Tabs or leads | $10.00 | PowerStream web store; stock not confirmed | Listed; currency unknown | No specific recollection. The report's claim that two of these fit either side of a central sensor does not hold once tabs and clearance are included (finding 4) | Viable only if the layout proves it. UNVERIFIED [S1] |
| 4 | SparkFun LiPo 40 mAh | PRT-13852 (cell DTP301120 per file names) | SparkFun / USA (Colorado); cell Data Power Technology / China | 3.7 V, 40 mAh, built-in protection, JST-PH lead | 20.0 x 11.0 x 3.0 (from an aggregator listing, not the SparkFun datasheet) | 2-wire; 3.0-4.2 V | $7.14 at 1; $6.78 at 25+ | SparkFun in stock (search summary). DigiKey 1568-13852-ND Active, 12-week lead; stock not seen. Arrow listing | Active | SparkFun's 1385x LiPo series exists and PRT-13852 is the 40 mAh member. The 301120 code implies 3.0 x 11 x 20 mm. No recollection of today's price or stock | Fallback in the first report; here promoted to co-candidate pending layout. UNVERIFIED [S5-S8] |
| 5 | TinyCircuits LiPo 40 mAh | ASR00072 | TinyCircuits / USA (Ohio) | 3.7 V, 40 mAh, 1.1 g, JST SH lead | 3.5+/-0.5 x 8.0+/-2.0 x 20.0+/-3.0 | 2-wire | $3.49 | TinyCircuits direct; stock not confirmed | Listed | TinyCircuits is in Akron, Ohio. No recollection of this item's dimensions | Rejected (thickness and tolerance). UNVERIFIED [S9] |
| 6 | Adafruit LiPo 100 mAh | 1570 | Adafruit / USA (New York) | 3.7 V, about 100 mAh, 3 g, JST-PH lead | 11.5 x 31 x 3.8 | 2-wire | Not seen | Adafruit direct; stock not seen | Listed | Agrees on capacity and dimensions | Rejected (3.8 mm). UNVERIFIED [S10] |
| 7 | Jauch LiPo with protection | LP501218JH+PCM+2 WIRE 50MM | Jauch Quartz / Germany | 3.7 V, 60 mAh | 20.0 x 12.5 x 5.4 | 2-wire | Not seen | DigiKey listing; stock not seen | Active (listed) | The 501218 code implies a 5.0 mm cell; consistent | Rejected (5.4 mm). UNVERIFIED [S11-S12] |
| 8 | Varta CoinPower Li-ion button cell | CP1254 A4 | Varta Microbattery / Germany | 3.7 V, 74-77 mAh, 1.6-1.8 g | dia 12.1 x 5.4 | Needs own protection | GBP 11.91 at 1 (UK) | No US listing seen | A4 current as of 2023 sheets | Agrees on dia 12.1 x 5.4 mm | Rejected (height; also a coin battery under 16 CFR 1263). UNVERIFIED [S13-S15] |
| 9 | Micro rechargeable coins and solid-state cells | class only | Seiko, Panasonic, TDK / Japan; ITEN / France | Capacity or pulse current 1-3 orders of magnitude short (report: from memory) | Not verified | - | Not checked | Not checked | Not checked | Agrees with the orders of magnitude (MS621FE about 5.5 mAh; CeraCharge about 0.1 mAh) | Rejected. UNVERIFIED [S2, S16] |
| 10 | Primary coin cell path | holders recalled by the report: Keystone 3002, 3034; MPD BK-912; Harwin S8411-45R | Keystone, MPD / USA; Harwin / UK | CR2016 about 90, CR2025 about 165, CR2032 about 225 mAh | Cells dia 20 x 1.6 / 2.5 / 3.2; with retainer about 2.4-4.3 (report estimate) | Needs boost and pulse buffering | Not checked | Commodity; not checked | Commodity | Agrees on cell capacities and IEC sizes. Holder heights not recalled | Rejected. UNVERIFIED [S16-S17] |
| 11 | TI BQ25100 linear charger | BQ25100YFPR (also BQ25100YFPT) | Texas Instruments / USA | 250 mA max, 4.20 V, 1 mA termination, 75 nA battery leakage, 4.45-6.45 V operating input, 30 V abs max input | 1.60 x 0.90 DSBGA; height <= 0.5 (report: from memory) | IN from cradle; ISET about 6.2 kohm for 22 mA; NTC on TS | Not verified | Not verified | "Newer version available" banner reported; status not confirmed | Agrees on title, 6-ball 1.6 x 0.9 mm package, 0.5 mm max height, 10-250 mA range, 1 mA termination, 75 nA, 30 V input rating, TS on bq25100 and CHG on bq25101, K_ISET 135 A.ohm, both order codes. Believed Active as of mid-2026. No knowledge of today's stock or price | Recommended. UNVERIFIED [S18-S21] |
| 12 | Charger / PMIC alternatives with ship mode | TI BQ25120A, BQ25180; Nordic nPM1300, nPM1304; ADI MAX77734 (order codes not given). Reviewer addition: TI BQ25155 | TI, ADI / USA; Nordic / Norway | Report (from memory): BQ25120A 5-300 mA + buck, 2.5 x 2.5 mm; BQ25180 with power path and ship mode, about 1.6 x 1.1 mm; nPM1300 32-800 mA; nPM1304 about 4-100 mA | Not verified | I2C | Not checked | Not checked | Not checked | Agrees with those figures. BQ25155 as recalled: 1.25-500 mA charge, termination to 0.5 mA, 10 nA ship mode, 12-bit ADC, LDO, about 2.0 x 1.6 mm WCSP | Fallback. UNVERIFIED |
| 13 | Microchip MCP73831 linear charger | MCP73831T-2ACI/OT | Microchip / USA | 4.20 V, 15-500 mA, SOT-23-5, no NTC input | SOT-23-5 about 2.9 x 2.8 x 1.45 | - | Not checked | Not checked | Not checked | Agrees; the order code is a real, long-standing one | Viable (second source). UNVERIFIED |
| 14 | TI TPS7A02 nano-power LDO | TPS7A0230PDQNR, TPS7A0228PDQNR, TPS7A0218PDQNR | Texas Instruments / USA | 25 nA quiescent, 200 mA, enable, active discharge on P versions | 1.0 x 1.0 x 0.4 X2SON | VBAT in; 3.0 V always-on, 2.8 V switched, 1.8 V optional | Not verified | Not checked | Not checked | Agrees on 25 nA, 200 mA, 1.5-6.0 V input, X2SON 1 x 1 x 0.4 mm. The code pattern is right; each individual voltage option must be checked for existence and stock. Output noise is high for a camera analog rail | Recommended for the always-on rail; review for the camera rail. UNVERIFIED |
| 15 | VBAT divider into MCU ADC | two 4.7 Mohm + 100 nF | Generic | 0.45 uA at 4.2 V | 0402 parts | - | Commodity | Commodity | n/a | Arithmetic confirmed (0.447 uA). Leakage sensitivity not addressed (finding 9). MAX17048 as recalled: 23 uA active, under 4 uA hibernate, 0.9 x 1.7 mm, voltage-only gauge | Recommended with lower or switched resistance. Arithmetic confirmed |
| 16 | Flush gold pads + pogo-pin cradle | pads custom; Mill-Max 0906 series, example 0906-0-15-20-76-14-11-0 (report: from memory) | Mill-Max / USA (New York) | Four pads, 5 V, about 22 mA | Pads about dia 2.5, flush | 5 V, current-limited | Not checked | DigiKey, Mouser (not checked) | Not checked | Mill-Max 0906 is a real spring-pin series and the example code has the right form; not confirmed. Pad polarity pattern needs correcting (finding 8) | Recommended with corrected pad pattern. UNVERIFIED |
| 17 | Input protection | TI TPD1E10B06DPYR; TI LM66100DCKR | Texas Instruments / USA | TVS 5.5 V working, 0402-size; ideal diode 1.5-5.5 V, about 150 nA | TVS about 1.0 x 0.6 x 0.5; LM66100 SC-70 about 2.0 x 2.1 x 1.1 | Series in the V line | Not checked | Not checked | Not checked | Agrees on both parts' descriptions and packages. LM66100's maximum input is about 6 V, which conflicts with the TVS clamp level and wastes the charger's 30 V rating (finding 8) | TVS recommended; replace LM66100 with a Schottky. UNVERIFIED |
| 18 | Wireless charging (Qi or NFC) | TI BQ51003; Renesas PTX30W (report: from memory) | TI / USA; Renesas / Japan | Qi coil and ferrite about 0.6-1.2 mm over dia 15-30 mm; NFC charging up to about 1 W | Not verified | - | Not checked | Not checked | Not checked | Agrees that both parts exist as described | Viable for a later generation. UNVERIFIED |
| 19 | USB-C receptacle on the puck | none | - | Shell about 3.2 mm high, 7-9 mm deep | about 9 x 7-9 x 3.2 | - | - | - | - | Agrees on shell height | Rejected. UNVERIFIED |

## 4. Key findings with confidence

Confidence is the reviewer's confidence after this pass. "Arithmetic confirmed" means recomputed locally from the first report's stated inputs. Inputs taken from datasheets or web listings remain UNVERIFIED.

1. **Energy budget.** Per read: 40.0 mAs = 0.0111 mAh (0.15 J at 3.7-3.8 V) nominal; 141.3 mAs = 0.0393 mAh (0.54 J) worst case. Per 4.5 h round: 0.689 mAh nominal, 2.975 mAh worst; reads are 81% and 79% of the round. Ten rounds plus 10 weeks off-state: 14.7 mAh nominal, 42.7 mAh worst. Arithmetic confirmed (the report's 42.5 is a rounding difference). The load inputs are the task's own ranges and no measurement exists. Confidence: high for the arithmetic, medium for the conclusion that a 40-45 mAh cell is the right size.

2. **Standby is the weak point, and one term is missing.** The off-state figure of 3.5-6.5 uA contains the protection circuit, LDO quiescent current and charger leakage, but no wake source and no display. If the product wakes when picked up and that is done with the IMU's wake-on-motion mode at the report's own 3-10 uA, off-state current is 6.5-16.5 uA, or 4.7-12.0 mAh per month. Ten rounds in 10 weeks then needs 19.8 mAh nominal and 59.5 mAh worst case. A nano-power wake accelerometer (sub-microamp class) or a Hall switch would restore the original figures. Separately, the protection IC alone at 3 uA takes 26 mAh per year (61% of the cell); at 6 uA, 53 mAh per year (more than the whole cell). A ship-mode PMIC does not reduce this, because the protection circuit is on the cell side of the switch. Shipped at 30% state of charge (12.9 mAh), the cell reaches cut-off in 2.3-3.8 months including 2% per month self-discharge (2.7-5.0 months excluding it). Confidence: high for the arithmetic; medium for the inputs (protection IC current is unknown for this pack).

3. **Thin cells.** The claim that PowerStream's GM series are the only catalog cells of 2.5 mm or less in a US sales channel could not be tested. It agrees with reviewer recollection that mainstream US hobby and distributor cells start at about 3 mm and that 2 mm cells are normally custom or semi-custom from Chinese makers. Plausibility check on the listed capacities: GM201030 at 43 mAh in 0.60 cm3 is 265 Wh/L; GM201021 at 22 mAh in 0.42 cm3 is 194 Wh/L; the 15 x 15 mm cell is 164 Wh/L; SparkFun PRT-13852 is 224 Wh/L. The GM201030 is the outlier on the high side for a 2 mm cell, where packaging overhead is proportionally largest. Scaling the GM201021 by active length (assuming about 4 mm of seal and tab overhead) gives about 34 mAh. Treat 43 mAh as a vendor claim to be measured. Confidence: low (UNVERIFIED listing; reviewer estimate).

4. **Cell placement geometry (reviewer estimate).** Assume a 42 mm puck with 1.5 mm side walls, so a 19.5 mm internal radius. A rectangular bay of length L with its outer long edge at distance y from the centre fits when L <= 2 x sqrt(19.5^2 - y^2).
   - GM201030-PCB, bay about 12 x 34 mm: the outer edge can be no further out than 9.6 mm, so the bay spans from -2.4 mm to +9.6 mm and covers the centre. It cannot sit beside a central grain sensor; it must be stacked above or below it. The first report says the same in a note.
   - 20 mm cell with protection tail, bay about 12.5 x 24 mm: outer edge at up to 15.4 mm, inner edge at 2.9 mm. It clears a central feature up to about 5.7 mm in diameter.
   - Two 15 x 15 mm cells either side of the centre: with a 6 mm central gap and no tab or clearance allowance, the outer corners land exactly on the 19.5 mm radius. With tabs and clearance they do not fit. The report's statement that this cell "packs well beside a central base sensor" is not supported.
   - Thickness: the side-lying camera modules already require a mid-layer several millimetres high. A 3.0 mm cell in a board cut-out needs a 3.4 mm bay within that layer and adds nothing to the stack; a 2.0 mm cell can sit over the board. The cut-out costs about 300 mm2 of roughly 1,190 mm2 of board area. Whether the 3.0 mm cell costs 0 or +1 mm is therefore a layout question, not a fixed penalty.
   Confidence: medium (geometry is exact; wall thickness, camera module size and protection-tail length are assumptions).

5. **Pulse current.** Worst-case simultaneous load is about 47 mA (MCU 15, cameras 10.7, IMU 0.9, one LED at 20), which is 1.1C on a 43 mAh cell. Small thin cells are commonly rated 1C continuous. With an assumed pack impedance of 1-5 ohm (reviewer estimate; it rises in the cold), the sag is 25-235 mV, which matters against a 3.05 V cut-off for a 3.0 V LDO. The cell's maximum discharge rating and impedance at 5 C are needed. Confidence: low (estimate).

6. **Coin and button cells are rightly rejected.** The CR-path arithmetic is confirmed: boost factor 3.0 / (2.6 x 0.85) = 1.357; 26 and 94 mAh at the rail become 35 and 128 mAh at the cell; 25 mA at the rail is 34 mA at the cell; with 10-40 ohm internal resistance the sag is 0.34-1.36 V. Cell capacities and sizes match reviewer recollection. Holder heights and the Varta CP1254 height (5.4 mm) are UNVERIFIED but match recollection for the Varta part. Confidence: medium-high for the conclusion.

7. **Charger.** The BQ25100 figures quoted (1.60 x 0.90 mm DSBGA, 1 mA termination, 75 nA leakage, 30 V input rating, 4.45-6.45 V operating input) match reviewer recollection of the TI datasheet but were not opened in this pass. Arithmetic: 135 A.ohm / 6.19 kohm = 21.8 mA; 0.5C of 43 mAh is 21.5 mA; 10% termination is 2.2 mA; dissipation at 5 V input is about 29 mW. The part has no power path and no ship mode, so system load during charging must stay below the termination current. Lifecycle, price and stock are UNVERIFIED. Confidence: medium.

8. **Contacts and input protection.**
   - Pad pattern: four pads at 90 degree spacing are 180-degree-safe only if opposite pads share a net (V-G-V-G around the circle). At a 90 degree mis-seat the polarity is reversed, which is why series reverse blocking is needed.
   - Reverse blocking: with one Schottky at about 0.3 V, the charger sees 4.7 V from a 5.0 V source and 4.45 V from a 4.75 V source, at or above the reported 4.45 V minimum. Two drops (a diode bridge) fall to 4.4 V and 4.15 V, so a bridge needs a cradle output of about 5.3 V or more. Arithmetic confirmed.
   - LM66100 (reviewer recollection, UNVERIFIED): a 1.5-5.5 V part with a maximum input near 6 V. Placed after a TVS that clamps at 10 V or more during a strike, it is the weakest part in the chain, and it removes the benefit of the charger's 30 V input rating. A 30-40 V Schottky in a sub-0.5 mm package avoids both problems and the 1.1 mm SC-70 height.
   - Pads at 0 V off the cradle (pull-down, no back-feed) is the right rule for corrosion. The cradle should apply 5 V only after it detects a seated puck.
   Confidence: high for the pad-pattern and headroom logic; low for the part-specific statements.

9. **Battery sense.** A 2 x 4.7 Mohm divider draws 0.447 uA at 4.2 V. Arithmetic confirmed. Its Thevenin resistance is 2.35 Mohm and, with 100 nF, its time constant is 0.24 s. Input leakage of 1 / 10 / 100 nA causes 4.7 / 47 / 470 mV of error referred to the battery. An open-circuit-voltage lookup needs about 10-20 mV accuracy on the plateau, so the leakage of the chosen ADC pin and of the capacitor must be below about 2-4 nA, or the divider should be 2 x 1 Mohm (2.1 uA) or switched. The conclusion that a gauge IC is not justified stands. One wording point: the MAX17048 is a voltage-only gauge, so the report's coulomb-counter argument applies to current-sensing gauges, not to it. Confidence: high.

10. **LDO rails versus a buck-boost.** 3.0 / 3.8 = 78.9%. A 90% buck-boost would draw 0.877 times the LDO's battery current, a saving of 12.3%. Arithmetic confirmed. Against a round budget of 0.7-3 mAh the saving is not worth an inductor. The 3.0 V rail depends on the display and camera supply ranges, which are set in other topics. A nano-power LDO has relatively high output noise; for the switched camera analog rail a low-noise LDO costs nothing in standby. Confidence: medium-high.

11. **Application-processor case.** 300 mW for 6 s is 1.8 J: 0.132 mAh drawn directly at 3.8 V, 0.146 mAh through a 90% buck, 0.167 mAh through a 3.0 V LDO. Per round 9.4-11.5 mAh, so 3.6-4.4 rounds from 41 mAh. Arithmetic confirmed. The 100 mA peak is 2.3C, so the cell would also have to be larger or higher-rate. Confidence: high for the arithmetic.

12. **Reese's Law.** The quoted definition (single-cell battery with diameter greater than height, or any other battery the Commission determines to be an ingestion hazard) and the "regardless of whether such batteries are intended to be replaced" wording match reviewer recollection of the statute and 16 CFR 1263.2. UNVERIFIED in this pass. The conclusion that a sealed product with a rectangular pouch cell is outside the rule remains the first agent's interpretation; confirm with a CPSC-accepted test lab. The UL 4200A test values in the report are from memory and remain UNVERIFIED. Confidence: medium for the definition, low for the test values.

13. **Charging interface choice.** Flush pads add no stack height; a Qi coil competes with the base grain window; a USB-C shell is about half the device thickness. These agree with reviewer recollection and with the geometry, but no part data was checked. Confidence: medium for the choice.

## 5. Verification table

Verdict key: confirmed = recomputed or logically checked here; corrected = the report's value or wording needs changing; contradicted = evidence found against it; unverifiable = needs a live source that could not be reached in this pass.

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | GM201030-PCB exists, is listed and purchasable from PowerStream today; 43 mAh; 2 x 10 x 30 mm; $12.00 | unverifiable | - | UNVERIFIED. www.powerstream.com not reachable. Capacity is high relative to GM201021 (265 vs 194 Wh/L). Overall length with protection board unknown. |
| 2 | SparkFun PRT-13852: 40 mAh, 20 x 11 x 3.0 mm, $7.14, DigiKey 1568-13852-ND Active | unverifiable | - | UNVERIFIED. www.sparkfun.com not reachable. Recollection: the product exists; the 301120 code implies those dimensions. |
| 3 | BQ25100YFPR exists, Active, purchasable; 1.60 x 0.90 mm DSBGA; 1 mA termination; 75 nA; 30 V input; 4.45-6.45 V | unverifiable | - | UNVERIFIED. www.ti.com not reachable. All figures match reviewer recollection. Lifecycle, price, stock not known. |
| 4 | BQ25100 ISET about 6.2 kohm for about 22 mA (K_ISET 135 A.ohm) | confirmed (arithmetic) | 6.19 kohm gives 21.8 mA | K_ISET value itself UNVERIFIED; matches recollection. |
| 5 | TPS7A0230PDQNR / TPS7A0228PDQNR / TPS7A0218PDQNR: 25 nA, 200 mA, 1.0 x 1.0 x 0.4 mm | unverifiable | - | UNVERIFIED. Family data matches recollection. Existence and stock of each voltage option must be checked. Consider a low-noise LDO for the switched camera rail. |
| 6 | TPD1E10B06DPYR and LM66100DCKR as input protection | corrected (design) | Keep the TVS; replace LM66100 with one 30 V or higher Schottky | Part data UNVERIFIED. Reasoning: LM66100 is a 5.5 V-class part behind a TVS that clamps higher, and it negates the charger's 30 V rating. Depends on recollection of LM66100's maximum input. |
| 7 | Mill-Max 0906-series spring pin, code 0906-0-15-20-76-14-11-0 | unverifiable | - | UNVERIFIED. Series exists per recollection; exact code not confirmed. Cradle part, not thickness-critical. |
| 8 | Four pads "V,V,G,G at 90 degrees" survive a 180 degree rotation | corrected | Alternating V-G-V-G; opposite pads share a net | Read as a sequence around the circle, V,V,G,G reverses polarity at 180 degrees. |
| 9 | PMIC fallbacks (BQ25120A, BQ25180, nPM1300, nPM1304, MAX77734) | unverifiable | - | UNVERIFIED. Descriptions match recollection. Reviewer adds BQ25155 as a candidate. A ship mode does not remove the pack protection IC's drain. |
| 10 | Per-read energy 0.011 / 0.039 mAh, 0.15 / 0.54 J | confirmed (arithmetic) | 0.0111 / 0.0393 mAh | 40.0 and 141.3 mAs. Inputs are the task's load ranges. |
| 11 | Per-round 0.7 / 3.0 mAh; reads about 80% | confirmed (arithmetic) | 0.689 / 2.975 mAh; 81% / 79% | - |
| 12 | 10 rounds incl. 10 weeks off-state = 15 / 43 mAh | corrected | 14.7 / 42.7 mAh as stated; 19.8 / 59.5 mAh if a 3-10 uA wake-on-motion IMU stays on | Arithmetic right, but the off-state omits any wake source. |
| 13 | Off-state 2.5-4.7 mAh per month; cut-off in "roughly 3-5 months" from 30% charge | corrected | 2.56-4.75 mAh per month; 2.3-3.8 months including self-discharge (2.7-5.0 excluding) | Protection IC current (3 uA) is an assumption. |
| 14 | Expected life: nominal about 20 rounds or 3 months; worst 8-10 rounds | corrected | Nominal about 36-48 rounds in 10 weeks or 7-12 months idle; worst 9.4 rounds new, 6.8 at end of life | From the report's own inputs. |
| 15 | Only catalog cells of 2.5 mm or less in a US channel are PowerStream GM-series | unverifiable | - | UNVERIFIED. Consistent with recollection; no search possible. |
| 16 | Varta CP1254 is 5.4 mm tall and cannot fit; no US distributor stock | unverifiable | - | UNVERIFIED. Height matches recollection. US stock claim not checked. |
| 17 | 16 CFR 1263.2 definition; applies to non-replaceable coin cells; pouch cell outside the definition | unverifiable | - | UNVERIFIED. Definition matches recollection. Pouch conclusion is an interpretation. |
| 18 | UL 4200A test values (1 m drops, 2 J impact, 330 N crush, 0.50 N.m, 72 N, 136 N) | unverifiable | - | UNVERIFIED. From memory in both passes. |
| 19 | Primary coin path: 35 / 128 mAh from the cell, 34 mA peak, 0.3-1.4 V sag | confirmed (arithmetic) | 35.3 / 127.6 mAh; 33.9 mA; 0.34-1.36 V | Cell capacities and internal resistance are from memory. |
| 20 | LDO costs about 12% versus a buck-boost | confirmed (arithmetic) | 12.3% | Assumes 3.8 V average cell voltage and 90% converter efficiency. |
| 21 | 2 x 4.7 Mohm divider draws 0.45 uA and is sufficient | corrected | 0.447 uA confirmed; 47 mV battery-referred error per 10 nA of leakage | Use 2 x 1 Mohm, a switched divider, or an internal supply channel. |
| 22 | Application processor at 300 mW for 6 s: about 0.13 mAh per read, about 4 rounds | confirmed (arithmetic) | 0.132-0.167 mAh per read; 3.6-4.4 rounds | Peak current 2.3C. |
| 23 | 3.0 mm fallback cell costs +1 mm of puck thickness | corrected | 0 to +1 mm depending on layout | In a board cut-out it shares the camera layer. Reviewer estimate. |
| 24 | Two 2 x 15 x 15 mm cells pack beside a central base sensor | corrected | Do not fit with tabs and clearance in a 19.5 mm internal radius with a 6 mm central gap | Reviewer geometry. |
| 25 | Schottky headroom: one drop clears 4.45 V, a bridge does not | confirmed (arithmetic) | 4.70 V at 5.0 V in; 4.45 V at 4.75 V in; bridge 4.40 / 4.15 V | 4.45 V minimum is UNVERIFIED. |
| 26 | Usable capacity about 41 mAh new, about 33 mAh at end of life | unverifiable | - | Estimates. 0.8 x 41 = 32.8 confirmed. Cold-temperature pulse sag may reduce the usable figure. |
| 27 | Qi stack height, USB-C shell height, MAX17048 currents | unverifiable | - | UNVERIFIED. Match recollection. Parts are not in the recommended design. |

## 6. Risks

1. **Verification gap.** Two passes have now failed to open a single datasheet or distributor page for the power parts. Every order code, package height, price, stock figure and lifecycle status is UNVERIFIED.
2. **Cell supply and data.** The thin cell is single-source, the listing's age is unknown, its capacity looks optimistic, and its protection board outline, protection IC, discharge rating and certification documents have not been seen. Prices of $10-13 per cell are high for production.
3. **Standby drain.** The protection IC and any always-on wake source dominate energy use in normal ownership. Without a 1 uA-class wake source and a low-quiescent protection IC, a puck left in a bag for a few months will be flat, and repeated deep discharge shortens cell life.
4. **Shelf deep-discharge.** From 30% charge the cell reaches cut-off in roughly 2-4 months. Packaging should carry a "charge before first use" instruction and the charger must recover a cell from protection cut-off.
5. **Pulse capability in the cold.** About 47 mA worst-case peak on a 43 mAh cell at 5 C may sag below LDO dropout before the cell is empty.
6. **Heat.** A sealed dark puck in sun or a parked car can exceed LiPo charge and storage limits. NTC-gated charging and a swell allowance are required; a reduced charge voltage may be worth the capacity loss.
7. **Processor choice.** A heavier vision processor cuts life to about 4 rounds and exceeds the likely discharge rating.
8. **Exposed contacts.** Thin or porous gold over nickel corrodes on wet, fertilised turf; debris fouls spring pins; a wet puck can bridge pads on the cradle. A 90 degree mis-seat reverses polarity.
9. **Sealing.** Printed walls can be porous and contact feed-throughs are leak paths. IP67 has not been designed or tested.
10. **Regulatory.** The pouch-cell reading of 16 CFR 1263 is an interpretation. Battery-charger energy rules (federal and California), California's battery-embedded product fee, battery transport rules and retailer safety-report requirements have not been researched.
11. **Rail assumptions.** If the round display needs 5 V, a boost converter and inductor return to the design.

## 7. Open questions

1. Can the listed hosts be allowed, or the search limit raised, so that datasheets and distributor pages can be opened? Until then nothing here is release-ready.
2. PowerStream GM201030-PCB: current price and stock, overall outline with protection board, protection IC and its quiescent current, maximum continuous and pulse discharge, impedance, cycle life, UN 38.3 test summary, IEC 62133-2 or UL 1642 report, production MOQ and lead time.
3. Which cell does the mechanical layout prefer: a 2.0 mm cell stacked over the centre, or a 3.0 x 11 x 20 mm cell in a board cut-out beside the grain sensor?
4. How does the puck wake, and what does the wake source draw? Is the display blank between rounds?
5. Which processor does the vision pipeline need, and what are its real active current and time per read?
6. What are the supply ranges of the chosen display and cameras? Is the round memory LCD a 3 V or 5 V part?
7. Can the BLE module be powered directly from the cell and measure its own supply, removing the main LDO and the divider?
8. What is the ADC input leakage of the chosen SoC pin, to size the battery divider?
9. Does the design include a magnetometer? If so, magnets stay in the cradle and the keeper material needs review.
10. Is a bare cell with on-board protection acceptable to the test lab and retailers, or must the protection circuit be part of the battery pack?
11. Do US DOE battery-charger standards and California battery-charger registration apply to a 0.16 Wh product charged from a USB-powered cradle, and what testing is needed? (Reviewer recollection says they apply to consumer battery chargers generally; UNVERIFIED.)
12. Does California's battery-embedded product law apply, and what notices and fees follow? (UNVERIFIED.)
13. Confirm with a CPSC-accepted lab that a sealed product with a non-replaceable rectangular pouch cell is outside 16 CFR 1263.

## 8. Sources

No URL was opened successfully in this verification pass. The list below is therefore in two parts.

Attempted in this pass and failed (host not reachable from the session):

- A1. https://www.powerstream.com/ultra-light.htm
- A2. https://www.ti.com/product/BQ25100
- A3. https://www.sparkfun.com/products/13852
- A4. https://www.ti.com/product/TPS7A02

Cited by the first report (seen by that agent as search-result summaries; NOT opened in this pass; listed so that a follow-up check can start from them):

- S1. https://www.powerstream.com/ultra-light.htm
- S2. https://www.powerstream.com/thin-lithium-ion.htm
- S3. https://visbis.com/categories/batteries/li-polymer/gm201030-pcb.html
- S4. https://visbis.com/categories/batteries/li-polymer/gm201030.html
- S5. https://www.sparkfun.com/products/13852
- S6. https://www.digikey.com/en/products/detail/sparkfun-electronics/PRT-13852/6605202
- S7. https://hotenda.com/product-detail/sparkfun-electronics-4519/prt-13852
- S8. https://robot-italy.com/en/products/prt-13852-polymer-lithium-ion-battery-40mah
- S9. https://tinycircuits.com/products/lithium-ion-polymer-battery-3-7v-40mah
- S10. https://www.adafruit.com/product/1570
- S11. https://www.digikey.dk/en/products/detail/jauch-quartz/LP501218JH-PCM-2-WIRE-50MM/13540125
- S12. https://www.digikey.com/en/product-highlight/j/jauch-quartz/lithium-polymer-batteries
- S13. https://texim-europe.com/getfile.ashx?id=134487
- S14. https://www.rapidonline.com/varta-88315101501-coinpower-button-cell-li-ion-3-7v-74mah-rechargeable-08-0956
- S15. https://asset.conrad.com/media10/add/160267/c1/-/en/002987803IN00/information-2987803-varta-knopfzellen-akku-cp1254-a4-li-ion-74-mah-37-v-1-st.pdf
- S16. https://www.ecfr.gov/current/title-16/chapter-II/subchapter-B/part-1263/section-1263.2
- S17. https://www.govinfo.gov/content/pkg/FR-2023-09-21/html/2023-20334.htm
- S18. https://www.ti.com/lit/gpn/BQ25100
- S19. https://www.ti.com/document-viewer/BQ25100/datasheet/detailed_description
- S20. https://www.ti.com/product/BQ25100A
- S21. https://www.radiolocman.com/datasheet/data.html?di=236995
- S22. https://www.govinfo.gov/content/pkg/FR-2023-09-21/html/2023-20333.htm
- S23. https://www.cpsc.gov/Business--Manufacturing/Business-Education/Business-Guidance/Button-Cell-and-Coin-Battery
- S24. https://www.compliancegate.com/reese-law/
- S25. https://www.buttonbatterylithium.com/ul-4200a-16-cfr-1263/

Local computation: the energy budget, standby sensitivity, shelf life, charger resistor, divider leakage, diode headroom, coin-cell path and bay geometry were recomputed with a short script during this pass. The formulas and inputs are given inline in sections 4 and 5 so that they can be reproduced.
