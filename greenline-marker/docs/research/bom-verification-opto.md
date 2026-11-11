# BOM verification: display, optics, battery, cradle, enclosure materials, fabrication

Date of check: 2026-11-11. Scope: 15 items of the GreenLine GL-1 bill of materials (group "opto").

## How this was checked

- Web search: 44 searches used (budget 45). Vendor pages could not be opened directly; the evidence is the text that the search tool extracted from the pages listed in section 5. Extracts are snapshots of unknown date, so every stock and price figure needs a live check before an order.
- Local KiCad 7 library (`/usr/share/kicad/footprints`, `/usr/share/kicad/symbols`): read directly for footprint names, pad numbering and descriptions. No 3D models are installed, so connector heights could not be taken from the library.
- Public GitHub repositories (read through `raw.githubusercontent.com`, files only, nothing executed): five hobby or research designs that use the LS013B7DH03, and three public VEMD8080 footprints. These are secondary sources. They are not a substitute for the manufacturer drawing.
- Status words: **confirmed** (source named), **corrected** (the given value was wrong or not the best orderable part), **not-confirmed** (no source seen; no number invented). Maker headquarters are general knowledge and were not source-checked in this session.

## 1. Summary

| # | Item | Final MPN | Status | Main point |
|---|---|---|---|---|
| 1 | Memory LCD | Sharp LS013B7DH03 | partly-verified | Outline, active area, pin order, 2.7-3.3 V and recommended connectors confirmed. Position of active area and FPC tail only from a public footprint. EXTCOMIN range differs between Sharp documents (54-65 Hz vs 1-60 Hz). 28-week lead time, stock snapshots conflict. |
| 2 | FPC connector 10-pos 0.5 mm | Molex 54548-1072 (given 54548-1071 is obsolete) | problem, corrected | The only KiCad footprint at or under 1.3 mm is Molex 54548-1071, which DigiKey lists as obsolete. 54548-1072 is active, same series. Bottom contact only. |
| 3 | Fold prism | Edmund Optics 32-526 | partly-verified | Dimensions, +/-0.1 mm tolerance, coating and price breaks confirmed. No lower-cost US source with a price was found (Tower Optical quotes only). |
| 4 | Li-polymer cell | PowerStream GM201030-PCB | partly-verified | 43 mAh, 2 x 10 x 30 mm, $12.00 and a UN38.3 note confirmed. Protection thresholds, size with board, UL 1642, IEC 62133 and stock not confirmed. No second US source at 2.2 mm or less. |
| 5 | Photodiode | Vishay VEMD8080 | partly-verified | Package, spectral range and stock confirmed. Pad layout and "one corner pad is the anode, seven pads are cathode" from three public footprints, not from the Vishay drawing. |
| 6 | Red LED 0402 | Vishay VLMS1500-GS08 | partly-verified | Electrical values from a distributor table. DigiKey stock not seen. |
| 7 | 850 nm LED 0402 | ams OSRAM SFH 4053 | partly-verified | Datasheet values confirmed. DigiKey stock and price not seen. |
| 8 | Cradle spring pin | Mill-Max 0914-0-15-20-77-14-11-0 (0906 does not fit the need) | problem, corrected | 0906 is a short-stroke solder-tail pin. 0914 is the long-stroke through-hole pin: 1.14 mm mid-stroke, 2.29 mm full stroke. Plunger diameter not confirmed. No press-fit version seen. |
| 9 | USB-C receptacle | GCT USB4105-GF-A | verified | Footprint in the KiCad library, DigiKey 2073-USB4105-GF-ACT-ND, $1.09 at 1. |
| 10 | Cover glass | Esslinger flat round mineral crystal 1.0 mm, size 28.0 | partly-verified | 12-40 mm in 0.1 mm steps, about $1.50-1.65 each. Diameter tolerance not stated. |
| 11 | 1.0 mm balls | McMaster-Carr 1598K16 (part number inferred) | partly-verified | 440C, Grade 25, pack of 250. Price not seen. No 316 ball at 1 mm found. |
| 12 | Tapes | 3M VHB 5907, 5909; 3M 468MP | partly-verified | Thicknesses confirmed. DigiKey sells 468MP rolls and quotes custom die cuts. No small-quantity laser converter confirmed. |
| 13 | Vent | W. L. Gore VE80205 | partly-verified | 2.0 mm inner, 5.0 mm outer, 104 ml/min at 70 mbar. Water entry pressure, IP rating and a US distributor not found. |
| 14 | PCB fabrication and assembly | n/a | partly-verified | 3.5 mil trace and space is outside the standard tier of every US fabricator checked. OSH Park cannot build it. |
| 15 | MJF PA12 printing | n/a | partly-verified | Vapor-smoothing minimum wall is 0.76 mm (Protolabs) to 1.0 mm (Xometry). The 0.55 mm roof ledge and 0.5 mm prism-pocket roof are below both. |

## 2. Concerns to act on first

1. **FPC connector is obsolete.** Molex 54548-1071 (the only 10-position, 0.5 mm, 1.2 mm-high footprint in the KiCad library) is marked obsolete at DigiKey and "no longer manufactured" at element14. Use Molex 54548-1072 (active, about 24,000 at DigiKey) and confirm on the Molex series drawing that the land pattern is the same.
2. **LCD contact side and pin mirroring are still open.** Sharp recommends both a bottom-contact and a top-contact connector. Public designs that plug the tail straight into a bottom-contact connector wire pin 1 = SCLK to connector pad 1. Two designs that use a different arrangement (one with a top-contact Molex 52745-1097) wire the reverse order, pad 1 = VSSA. The GL-1 fold (S-bend or U-fold under the glass) decides which applies. A wrong choice mirrors all ten pins.
3. **LS013B7DH03 supply.** Active at DigiKey and Arrow, but factory lead time is 28 weeks, Arrow, Future and Avnet show zero stock, the Mouser page says obsolete and not sold, and DigiKey stock snapshots disagree (about 2,437 on some regional pages, 0 on others). Buy EVT and DVT quantities as soon as a live page shows stock.
4. **EXTCOMIN rate.** One Sharp spec revision (LD-28410A) gives 54-65 Hz. Sharp's application information and an older spec give 1-60 Hz. The planned 64 Hz is inside the first range and outside the second. 60 Hz (32768 / 546) is inside both. Keep the rate a build constant and read the current spec (LD-2023X05, October 2023) before release.
5. **Battery compliance and second source.** Only a UN38.3 note was found for GM201030. No UL 1642 or IEC 62133 statement, no protection thresholds, no maximum current for the protected version, no length with the protection board, no stock figure. No other 2 mm protected cell was found at DigiKey, Mouser, Adafruit or SparkFun.
6. **PCB rules.** 3.5 mil (0.09 mm) needs the custom or advanced tier everywhere: AdvancedPCB standard is 5/5 mil, Sierra standard 4 mil, Bay Area Circuits standard 4 mil. Mask-plugged vias and ENIG are custom-tier at AdvancedPCB. Relaxing the fine areas to 4/4 mil (0.10 mm) would put the board in the standard tier at Sierra and Bay Area Circuits.
7. **MJF thin walls.** Stated vapor-smoothing minimums are 0.762 mm (Protolabs), about 1 mm (Xometry) and 1.5 mm for uniform results (Fictiv). The 1.0 mm side wall is acceptable, the 0.8 mm roof is marginal, the 0.55 mm roof ledge and the 0.5 mm roof over the prism pockets are below every stated minimum. Stated MJF tolerance is +/-0.2 to +/-0.3 mm, which is large against the 0.15 mm gaps in the height stack.
8. **Prism tolerance and price.** Edmund 32-526 has a +/-0.1 mm dimensional tolerance on a 2.0 mm leg and costs $105 at 1-5. No cheaper US source could be priced.
9. **Cradle pins.** The Mill-Max 0906 named in the design is a short-stroke solder-tail part. The 0914 long-stroke series meets the 1.0-1.5 mm working-travel need. Solder the pins into the cradle board instead of pressing them into a printed part.
10. **Vent.** Gore VE80205 is the smallest adhesive vent found, but its water entry pressure, IP rating and a US distributor are not confirmed.

## 3. Item detail

### 3.1 Sharp LS013B7DH03 memory LCD (priority item)

| Field | Value | Status and source |
|---|---|---|
| MPN | LS013B7DH03 | confirmed: DigiKey listing [W2] |
| Maker, HQ | Sharp Corporation, Japan | general knowledge, not source-checked |
| Lifecycle | Active at DigiKey and Arrow; Octopart "Production". Mouser page shows "Obsolete" and "not presently sold in your region" (page looks stale). A spec revision LD-2023X05 dated 17 Oct 2023 is referenced by a public design [G1] | confirmed active at two distributors [W2, W9]; conflict noted [W8] |
| DigiKey | 425-2903-ND. Stock about 2,436-2,437 on the Japan, Taiwan and Finland pages; 0 with "check lead time" on the Belgium and Ireland pages. US page extract: $11.42 at 1, $8.82 at 10. Manufacturer lead time 28 weeks | stock and price as seen in extracts, snapshot dates unknown; price at 100 and 1000 not-confirmed [W2] |
| Mouser | 852-LS013B7DH03: listed obsolete, not sold; no price | confirmed as seen [W8] |
| Future | 0 stock, 28-week factory lead time, $6.23 at 2,240 or more | confirmed as seen [W7] |
| Arrow | Active, no stock, 28 weeks, $6.284 at 2,240 | confirmed as seen [W9] |
| Avnet | 0 in US (aggregator figure) | not-confirmed (aggregator only) |
| Outline | 26.6 x 30.3 mm, tolerance +/-0.2 mm on both | confirmed: Sharp spec and application information [W3, W5] |
| Thickness | 0.741 mm in the Sharp spec table; 0.746 mm in the Sharp brochure and application information | confirmed, two values in Sharp documents; the design's 0.746 is the larger one [W3, W5, W6] |
| Active area | 23.04 x 23.04 mm | confirmed [W3] |
| Position of active area on the glass | Centred left-right: 1.78 mm each side. 1.55 mm from the edge opposite the tail. 5.71 mm from the tail edge | not-confirmed against the Sharp drawing. Values are from a public KiCad footprint that cites the 2023 Sharp spec [G1]. The Sharp drawing callout "13.30 +/-0.15" (half the width) was seen in an extract [W5] |
| FPC tail | Leaves the middle of one 26.6 mm edge (the edge with the 5.71 mm margin). In the public footprint: root 9.47 mm wide for about 5.7 mm, then a 5.5 mm wide tongue; 12.17 mm from the glass edge to the mouth of the connector, so the tail is roughly 13-15 mm long | not-confirmed against the Sharp drawing [G1] |
| Contact side of the tail | Inferred: contacts on the rear face (away from the viewer). Two designs plug the tail straight into a connector beside the face-up display with the straight pin order, one of them with a bottom-contact Hirose FH12 [G1, G2] | not-confirmed (inference from public designs) |
| Pin order on the tail | 1 SCLK, 2 SI, 3 SCS, 4 EXTCOMIN, 5 DISP, 6 VDDA, 7 VDD, 8 EXTMODE, 9 VSS, 10 VSSA | confirmed: Sharp "Input terminals and functions" table matched in a search extract [W4]; same order in three public designs [G1, G2, G3] |
| Mirroring risk | Two public designs wire the reverse order at the connector (pad 1 = VSSA ... pad 10 = SCLK): Molex 52745-1097 top contact [G4] and Molex 503480-1000 [G5] | confirmed that both wirings exist; which one GL-1 needs is not-confirmed |
| Connector recommended by Sharp | SMK FP12 series: CFP-4610-0150F (bottom contact) and CFP-4510-0150F (top contact) in spec LCP-1112045. Panasonic AYF531035 in the older spec LD-26X06A | confirmed [W3] |
| Supply | VDD and VDDA 2.7 V min, 3.0 V typ, 3.3 V max. Not a 5 V part | confirmed [W4] |
| EXTCOMIN frequency | 54-65 Hz in spec revision LD-28410A; 1-60 Hz in the application information and in older spec LCP-2111042. Notes: period must be constant; EXTCOMIN frequency must be below the frame frequency | two ranges confirmed as published; which one is current is not-confirmed [W10] |
| Operating temperature | -20 to +70 C (panel surface), storage -30 to +80 C in most copies. An older spec and the Mouser attribute say -10 to +60 C | confirmed with a conflict between revisions [W4] |
| EXTMODE high = connect to VDD | yes | confirmed [W4] |

Connector pad mapping seen in public designs (pad numbers are those of each design's connector footprint):

| Design | Connector | Contact side | Pad 1 ... pad 10 |
|---|---|---|---|
| samp38/varioSmooth [G2] | Hirose FH12-10S-0.5SH, KiCad library footprint | bottom | SCLK, SI, SCS, (EXTCOMIN tied to GND), DISP, 3V3, 3V3, (EXTMODE tied to GND), GND, GND |
| captainchapster/Eigentime32 [G3] | Panasonic AYF531035 | as recommended by Sharp | SCLK, SI, SCS, EXTCOMIN, DISP, VLCD, VLCD, VLCD, GND, GND |
| fearedspark/digital-level [G1] | Panasonic AYF531035, display drawn face-up beside the connector | as recommended by Sharp | symbol pins 1 SCLK ... 10 VSSA |
| TUDSSL/FreeBie rev4 [G4] | Molex 52745-1097 | top | GND, GND, VCC, VCC, VCC, VCC, EXTCOMIN, SCS, SI, SCLK |
| alx-alexpark/watch [G5] | Molex 503480-1000 | not checked | VSSA, VSS, EXTMODE, VDD, VDDA, DISP, EXTCOMIN, SCS, SI, SCLK |

None of these designs was confirmed as built and working.

### 3.2 FPC connector, 10 positions, 0.5 mm pitch

Footprints for 10 positions in `/usr/share/kicad/footprints/Connector_FFC-FPC.pretty` (confirmed by reading the files):

| Footprint | Pitch | Contact side in the description | Height in the description | Body outline on F.Fab |
|---|---|---|---|---|
| Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal | 0.5 mm | not stated | not stated | 8.10 x 5.60 mm |
| Molex_54548-1071_1x10-1MP_P0.5mm_Horizontal | 0.5 mm | "10 bottom-side contacts" | "1.2mm height" | 10.20 x 4.55 mm |
| TE_1-1734839-0_1x10-1MP_P0.5mm_Horizontal | 0.5 mm | "10 top-side contacts" | not stated | 10.43 x 4.40 mm |
| Molex_200528-0100, TE_1-84952-0, TE_1-84953-0 | 1.0 mm | not applicable | not applicable | wrong pitch |

In all three 0.5 mm footprints pad 1 is at x = -2.25 mm and pad 10 at x = +2.25 mm.

| Part | Maker, HQ | Lifecycle | Contact, height | US distributor, stock, price | Status |
|---|---|---|---|---|---|
| Molex 54548-1071 (0545481071) | Molex, USA | Obsolete at DigiKey; "No Longer Manufactured" at element14; Molex page says not formally published in the catalog | bottom, 1.20 mm | DigiKey product 3196999; one extract shows 13,454 in stock at $7.06, not reliable | problem [W11, W12] |
| **Molex 54548-1072 (0545481072)** | Molex, USA | Active at DigiKey | bottom, 1.20 mm (0.047 in) | DigiKey product 16629956; 24,056 in stock; lead time 10-17 weeks; USD price not seen (ZAR 25.14 at 3,000 on the South Africa page) | corrected, recommended [W12] |
| Hirose FH12-10S-0.5SH(55) | Hirose Electric, Japan | Active at DigiKey | bottom; max height 2 mm (Future) | DigiKey HFJ110CT-ND; about 19,760-20,546 in stock; $1.39 (aggregator); lead time 12 weeks | confirmed, too tall for the 1.3 mm limit [W14] |
| TE 1-1734839-0 | TE Connectivity, Switzerland | Active at Octopart and Future; TE's China page marks it discontinued (June 2025) | top; height not-confirmed | DigiKey A100293CT-ND; stock not seen; lead time 4 weeks | not-verified, lifecycle disputed [W13] |

Open points: the land pattern of 54548-1072 against the 54548-1071 footprint is not-confirmed (same series, drawing not seen). If the tail is folded so that a top-contact connector is needed, the KiCad library has no top-contact footprint at or under 1.3 mm. Candidates outside the library, none checked for footprint: Molex 54550-1071/-1072 (top contact, DigiKey listing seen), Hirose FH12A-10S-0.5SH(55) (top contact, DigiKey listing seen), SMK CFP-4510-0150F and Panasonic AYF531035 (Sharp's recommendations).

### 3.3 Edmund Optics 32-526 prism (priority item)

| Field | Value | Status and source |
|---|---|---|
| Stock number | 32-526, "2mm Aluminum Coated N-BK7 Right Angle Prism" | confirmed [W15] |
| Maker, HQ | Edmund Optics, USA | general knowledge |
| Dimensions | Legs 2.00 mm, hypotenuse 2.80 mm | confirmed [W15] |
| Tolerance | Dimensional +/-0.1 mm. Angle tolerance and surface quality not seen | confirmed for dimensions; rest not-confirmed [W15] |
| Coating | Protected aluminium on the hypotenuse, 400-2000 nm. Legs: not stated for this number. A separate "Aluminum & MgF2 coated" 2 mm version exists | confirmed [W15] |
| Price (US page) | $105.00 at 1-5, $94.50 at 6-25, $78.50 at 26-49 | confirmed as seen [W15] |
| Stock | "20+ in stock" at the snapshot | confirmed as seen [W15] |
| Lower-cost US source | Tower Optical (Florida): MPCH-0.7 (0.7 mm, enhanced aluminium) and MPU-2.0 (2.0 mm uncoated) are listed; an MPCH-2.0 listing was not found; price by quotation only (sales@toweroptical.com, 1-561-740-2525) | not-confirmed, no price indication [W16] |
| Price benchmark | Edmund 47-922, 2 mm aluminised and AR-coated N-SF11 micro prism, $176.00 | confirmed as seen; it is dearer, not cheaper [W16] |

### 3.4 PowerStream GM201030-PCB cell (priority item)

| Field | Value | Status and source |
|---|---|---|
| MPN | GM201030-PCB (bare cell GM201030) | confirmed: PowerStream list [W17] |
| Seller, HQ | PowerStream Technology, Utah, USA. Cell factory not named | seller confirmed [W17]; cell maker not-confirmed |
| Capacity, voltage | 43 mAh, 3.7 V | confirmed [W17] |
| Dimensions | 2 x 10 x 30 mm as listed. Size with protection board, tab fold and leads | listed size confirmed; size with board and leads not-confirmed |
| Maximum discharge | Thin-cell family data: about 90 % of capacity at 100 mA, about 86 % at 200 mA. Limit of the protection board not given | family data confirmed [W18]; value for this part not-confirmed |
| Protection thresholds | PowerStream says the board prevents over-discharge, short circuit and unsafe charge voltage. No numbers | not-confirmed [W17, W18] |
| Operating limits | End of discharge 2.8 V; charge 0-45 C; discharge -20 to +60 C | confirmed for the family [W18] |
| UN38.3 | Noted against GM201030 in a PowerStream table (older table) | confirmed as seen [W18] |
| UL 1642, IEC 62133 | No statement found | not-confirmed |
| Price | $12.00 each with board; $10.00 bare. Further figures $8.20, $4.95, $3.80, $3.38 appear without readable quantity labels | confirmed as seen; quantity breaks not-confirmed [W17] |
| Stock | Not shown. PowerStream notes that factories do not hold stock | not-confirmed |
| Alternative at 2.2 mm or less | None found at DigiKey, Mouser, Adafruit or SparkFun. PowerStream PGEB021235 (2 x 12 x 35 mm, 40 mAh) is the same seller. CM Batteries 55 mAh pack is 2.5 mm thick | none found [W19] |

### 3.5 Vishay VEMD8080 photodiode

| Field | Value | Status and source |
|---|---|---|
| MPN | VEMD8080 | confirmed [W20] |
| Maker, HQ | Vishay Intertechnology, USA (opto division in Germany) | general knowledge |
| Lifecycle | Listed with stock at DigiKey; no lifecycle flag seen | not-confirmed |
| Package | 4.8 x 2.5 x 0.48 mm, 8 pads, no leads; sensitive area 4.5 mm2 | confirmed: Vishay datasheet extract [W20] |
| Spectral range | 350-1100 nm; listed as an 850 nm part, 130 degree, 70 ns | confirmed [W20] |
| Dark current | 0.2 nA (LCSC, likely typical) and 10 nA max (DigiKey) | partly confirmed [W20] |
| Pad layout | 8 pads of 0.55 x 0.55 mm at x = +/-2.00 and +/-0.69 mm, rows at y = +/-1.19 mm | not-confirmed against the Vishay drawing; three public footprints agree [G6, G7, G8] |
| Cathode | Seven pads are cathode; the anode is one corner pad (pad 5 in the SamacSys numbering, at x = +2.00, y = -1.19 in that footprint) | not-confirmed against the Vishay drawing; two public libraries agree [G6, G7] |
| Stock, price | DigiKey product 8602378: 3,777 in stock, 3.61 at 1 on the Canada page (CAD). LCSC 948. Lead time 9-16 weeks | confirmed as seen; USD breaks not-confirmed [W20] |
| KiCad footprint | None for VEMD8080. Photodiode footprints present: Osram_SFH2430, Osram_SFH2440, Osram_BPW34S-SMD, Osram_BP104-SMD (SMD DIL 4.5 x 4 mm), Osram_SFH2201 (4 x 5.09 mm). Their heights are not in the library and were not checked | confirmed locally; suitability not-confirmed |

### 3.6 Vishay VLMS1500-GS08 red LED

| Field | Value | Status and source |
|---|---|---|
| MPN | VLMS1500-GS08, super red, AlInGaP | confirmed [W21] |
| Maker, HQ | Vishay, USA | general knowledge |
| Lifecycle | "Production" at Octopart. RS says it will stop stocking it | partly confirmed [W21] |
| Package | 0402, 1.0 x 0.5 mm, height 0.35 mm | confirmed (datasheets.com summary) [W21] |
| Wavelength | 631 nm in a specification table (column unlabeled, likely dominant); 639 nm in a listing (likely peak) | partly confirmed [W21] |
| Forward voltage | 2.0 V typ, 2.4 V max at 20 mA | confirmed (table extract) [W21] |
| Luminous intensity | 18 mcd min, 54 mcd typ at 20 mA | confirmed (table extract) [W21] |
| Viewing angle | 130 degrees | confirmed (distributor listing) [W21] |
| Stock, price | DigiKey not seen. About $0.092 (Octopart), $0.156 at 1 (Quest, 142 pieces) | not-confirmed for DigiKey |
| KiCad footprint | LED_SMD:LED_0402_1005Metric present | confirmed locally |

### 3.7 ams OSRAM SFH 4053 infrared LED

| Field | Value | Status and source |
|---|---|---|
| MPN | SFH 4053 (a newer SFH 4053B also appears on the maker's site) | confirmed [W22] |
| Maker, HQ | ams-OSRAM AG, Austria | general knowledge |
| Lifecycle | Listed at DigiKey, element14, RS; no flag seen | not-confirmed |
| Package | 1.0 x 0.5 x 0.45 mm | confirmed: datasheet version 1.4 [W22] |
| Wavelength | Peak 860 nm, centroid 850 nm | confirmed [W22] |
| Forward voltage | 1.6 V at 70 mA | confirmed (DigiKey title) [W22] |
| Radiant intensity | 7 mW/sr at 70 mA; 140 degree | confirmed [W22] |
| Stock, price | DigiKey product 2713572, figures not shown. RS $0.619 at 10-740. Cytech $0.732 reference. element14 1,085 in stock | DigiKey not-confirmed [W22] |

### 3.8 Mill-Max spring pin for the cradle

| Field | 0906-0-15-20-76-14-11-0 (as named in the design) | 0914-0-15-20-77-14-11-0 (better suited) |
|---|---|---|
| Maker, HQ | Mill-Max Mfg. Corp., USA (general knowledge) | same |
| Type | Through-hole solder tail, "short stroke". Not press-fit: confirmed [W23] | Through-hole standard tail, "long stroke": confirmed [W25] |
| Lifecycle | Active at DigiKey: confirmed [W23] | Listed at DigiKey and element14; flag not seen |
| Stroke | Values unreadable in the extract; .0275 in mid and .055 in max were read for the sibling short-stroke rows: not-confirmed | Mid-stroke .045 in (1.14 mm), full stroke .090 in (2.29 mm): confirmed (Mouser series page) [W25] |
| Length | Overall 5.24 mm; maximum working height 3.48 mm: confirmed [W23] | Overall 8.3 mm; maximum working height 6.96 mm; recommended working height 5.82 mm: confirmed [W25] |
| Force | 25 g initial, 60 g at working travel: confirmed [W23] | 60 g at working travel: confirmed [W25] |
| Plunger diameter | 1.07 mm (.042 in) seen for the sister part 0906-8: not-confirmed for this part | not-confirmed |
| Body diameter | not-confirmed | not-confirmed |
| Current | 2 A (Farnell); 2 A continuous, 3 A peak for the sister part: confirmed [W23] | not-confirmed (2 A seen for the neighbouring 0913) |
| Stock, price | DigiKey product 1147048; price not seen | DigiKey ED8185-ND (truncated extract), lead time 4 weeks; element14 China 20,672; price not seen |

Result: 0906 does not give 1.0-1.5 mm working travel if the short-stroke figures apply. Use the 0914 long-stroke pin, and solder it into the cradle's 2-layer board. A 1.07 mm plunger would pass a 2.2 mm hole with 0.56 mm radial clearance, but the 0914 plunger diameter must be read from the Mill-Max drawing. The 085X "power" series has the same stroke with 120 g force [W24]; no press-fit version of any series was seen.

### 3.9 USB Type-C receptacle

| Field | Value | Status and source |
|---|---|---|
| MPN | GCT USB4105-GF-A (variants -060 and -120 are separate order codes) | confirmed [W26] |
| Maker, HQ | GCT (Global Connector Technology) | HQ not-confirmed |
| KiCad footprint | Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal; description "USB 2.0 Type C Receptacle, GCT, 16P, top mounted, horizontal, 5A"; tags include USB4105-GF-A. Symbol Connector:USB_C_Receptacle_USB2.0_16P present | confirmed locally |
| DigiKey | 2073-USB4105-GF-ACT-ND; $1.09 at 1, $0.917 at 10, $0.86 at 25; about $0.57 at 8,000 on reel; lead time 9 weeks; an aggregator shows 127,697 in stock | price confirmed as seen (DigiKey Singapore page in USD); stock from an aggregator; price at 100 and 1000 not-confirmed [W26] |
| Body dimensions | not seen | not-confirmed |

### 3.10 Cover glass

| Field | Value | Status and source |
|---|---|---|
| Source | Esslinger (USA), "Watch Crystal Flat Round Standard Mineral Glass Crystal 1mm Thick", SKU family 201100 | confirmed [W27] |
| Sizes | 12 mm to 40 mm in 0.10 mm steps, sold singly. 28.0 mm is inside the range | confirmed [W27] |
| Price | $1.65 on one page, $1.50 on another; 5 % off at 10-49, 10 % at 50-99, 15 % at 100 or more. Price for size 28.0 not shown separately | confirmed as seen [W27] |
| Diameter and thickness tolerance | not stated | not-confirmed |
| Other houses | Jules Borel: only a sapphire 28.0 x 1 mm crystal seen ($11.00 at 1-2, $10.45 at 3-9, $9.90 at 10 or more). Otto Frei and Cas-Ker: no result | not-confirmed for mineral glass [W27] |

### 3.11 Stainless balls, 1.0 mm

| Field | Value | Status and source |
|---|---|---|
| Source | McMaster-Carr | confirmed [W28] |
| Part number | 1598K16 (read from run-together listing text; confirm on the page) | not-confirmed |
| Material, grade | 440C stainless, Grade 25, diameter tolerance +/-0.0025 mm, Rockwell C58, ISO 3290, magnetic | confirmed [W28] |
| Pack, price | Pack of 250; price not seen | pack confirmed; price not-confirmed |
| 316 stainless at 1 mm | not found | not-confirmed |

### 3.12 Adhesive tapes

| Tape | Thickness | Status and source |
|---|---|---|
| 3M VHB 5907 | 0.008 in (0.20 mm), black, acrylic foam, tolerance +/-15 % | confirmed: 3M data sheet extract [W29] |
| 3M VHB 5909 | 0.012 in (0.30 mm), black | confirmed [W29] |
| 3M VHB 5906, 5908 (same family) | 0.15 mm, 0.25 mm | confirmed [W29] |
| 3M 468MP (200MP adhesive transfer tape) | 5 mil (0.13 mm); DigiKey lists 0.132 mm | confirmed [W30] |

US sources: DigiKey stocks 468MP rolls and sheets (examples seen: 468MP-1-5, 468MP-4-5, 468MPSQ-12-6) and lists "3M Custom Die Cuts" that need a manufacturer-approved quote, a standard package quantity, and cannot be cancelled [W30]. DigiKey has a product page for thin VHB 5906-5915 [W29]. TBP Converting hosts the 5906-5909 data sheet [W29]; its location and minimum order were not checked. No small-quantity laser-cutting converter was confirmed. Note for the stack: the 0.15 mm LCD adhesive frame matches VHB 5906 (0.15 mm) or 468MP (0.13 mm); the 0.2 mm cover-glass ring matches 5907.

### 3.13 Pressure-equalisation vent

| Field | Value | Status and source |
|---|---|---|
| MPN | W. L. Gore VE80205 (adhesive series VE8), described as the smallest footprint in the Gore protective vent line | confirmed [W31, W32] |
| Maker, HQ | W. L. Gore & Associates, USA; RS lists country of origin Germany | HQ general knowledge; origin confirmed as seen |
| Size | 2.0 x 5.0 mm. Venting area 3.14 mm2 (a 2.0 mm circle); adhesive ring 16.49 mm2 (2.0 mm inner, 5.0 mm outer); thickness 0.26 mm | confirmed; the areas check arithmetically against 2.0 and 5.0 mm [W31, W32] |
| Required hole | not stated. The venting diameter is 2.0 mm, so the housing hole should not exceed 2.0 mm, on a flat pad larger than 5.0 mm | not-confirmed (inference) |
| Airflow | 104 ml/min typical at 70 mbar | confirmed [W31] |
| Water entry pressure, IP rating | not found for VE8. A Gore factsheet gives IP66 and IP68 for the black VE7 series | not-confirmed [W32] |
| Membrane | Oleophobic ePTFE, acrylic adhesive, white, UL 94 VTM-0 | confirmed (Octopart listing) [W32] |
| Packaging | 5 parts per 41 mm carrier; RS sells packs of 50 | confirmed [W31, W32] |
| US source | none found (RS UK and Sweden, Distrelec for VE70205) | not-confirmed |

### 3.14 PCB fabrication and assembly (priority item)

Requirement: 4 layers, 0.8 mm (0.031 in), 0.09 mm (3.5 mil) trace and space in limited areas, 0.25 mm drill, ENIG, plugged and tented vias.

| Fabricator | Trace and space | Drill or hole | 0.031 in thickness | ENIG | Plugged vias | Tier needed for GL-1 | Status and source |
|---|---|---|---|---|---|---|---|
| AdvancedPCB (formerly Advanced Circuits) | Standard 5/5 mil; custom down to 2.75/3 mil. Corporate PDF: .003 in standard, .002 in advanced | Standard 0.010 in; custom 0.004 in | Standard option | Listed as a custom surface finish | Mask-plugged vias: not in standard, yes in custom | Custom spec (quoted) | confirmed [W33, W34] |
| Sierra Circuits | Standard product 4 mil; FAQ: typically 3 mil minimum; HDI tables 3-3.5 mil | Mechanical drill 5.9 mil minimum | Range .005-.250 in on a page not specific to 4-layer rigid | Offered | not found | Above the standard product; tier name not-confirmed | partly confirmed [W35] |
| Bay Area Circuits | 0.004 in standard, 0.002 in advanced (capabilities PDF dated December 2025) | Finished hole 0.006 in standard, 0.004 in advanced for boards 0.031 in or thinner | Within range | Yes in both tiers | Via fill not found | Advanced for 3.5 mil; standard if relaxed to 4 mil | confirmed [W36] |
| Royal Circuits (now Summit Interconnect) | Royal: 3/3 mil general, 6/6 mil for its 1-6 layer tier (old pages). Summit: .003/.003 in is "advanced" on half-ounce inner layers | Summit: .006 in standard, .005 in advanced, .004 in emerging. Royal 1-6 layer tier: 8 mil | "Full range" | Yes | Via-in-pad and epoxy fill for 8 mil vias and larger | Advanced; quick-turn tier figures not found | partly confirmed, old pages [W37] |
| OSH Park 4-layer | 5/5 mil | 10 mil minimum drill, 4 mil annular ring | Not offered: 63 mil (1.6 mm) nominal seen for 4-layer; 0.8 mm exists only as a 2-layer 2 oz service | ENIG, FR408 | not offered | Cannot build this board | confirmed for trace and drill; 4-layer prototype thickness table not readable [W38] |

Assembly houses for a 0.5 mm-pitch 25-ball CSP and 0402 parts on both sides, prototype quantities:

| House | Stated capability | Status and source |
|---|---|---|
| MacroFab (USA) | BGA, FBGA, LGA to 0.4 mm ball pitch; X-ray inspection; double-sided assembly | confirmed [W39] |
| AdvancedPCB assembly (USA) | No minimum order; BGA, micro-BGA, VFBGA and CSP placement; 3D X-ray. No numeric pitch limit given | partly confirmed [W39] |
| Screaming Circuits, CircuitHub, Sierra Circuits assembly | no result | not-confirmed |

### 3.15 Multi Jet Fusion PA12, dyed black, vapor smoothed

| Bureau | Minimum wall (MJF) | Tolerance | Vapor smoothing | Status and source |
|---|---|---|---|---|
| Protolabs | 0.8 mm recommended minimum; 2.5-4.0 mm ideal | not seen | Offered. Minimum wall 0.030 in (0.762 mm); consistent wall thickness advised. Black dye is standard for MJF | confirmed [W40, W42] |
| Xometry | Pages differ: 0.6 mm supported and 0.7 mm unsupported; 0.7 mm; 0.8 mm minimum with 1.5 mm recommended; 0.5 mm minimum with 1.5 mm recommended | +/-0.3 % with a lower limit of +/-0.2 mm or +/-0.3 mm (pages differ) | About 1 mm recommended minimum because thinner sections can bubble or bridge. US-made option not found in results | partly confirmed [W41, W42] |
| Fictiv | not seen | not seen | Walls under 1.5 mm do not process as uniformly | confirmed [W42] |
| Hubs (Protolabs Network) | not seen | not seen | Thin walls and sharp edges may be unsuitable; dyed black PA12 offered | confirmed [W42] |
| Forecast 3D, Endeavor 3D, DI Labs | no result | no result | no result | not-confirmed |

Indicative third-party figure for an HP 5200 with PA12: XY +/-0.25 mm on features to 30 mm, Z +/-0.42 to 0.60 mm on features to 80 mm [W40].

Against the GL-1 tub and base: 1.0 mm side wall and 1.0 mm base plate meet every stated minimum except Fictiv's uniformity advice. The 0.8 mm roof is 0.04 mm above the Protolabs vapor-smoothing minimum and below Xometry's. The 0.55 mm roof ledge and the 0.5 mm roof over the prism pockets are below every stated minimum.

## 4. Fields that stayed unconfirmed

- LS013B7DH03: position of the active area, FPC tail geometry and contact side from the Sharp drawing; current EXTCOMIN range; live DigiKey stock; price at 100 and 1000.
- Molex 54548-1072: land pattern identity with 54548-1071; USD price.
- Edmund 32-526: angle tolerance, surface quality, coating of the legs.
- Tower Optical: existence of MPCH-2.0 as a catalog part and any price.
- GM201030-PCB: everything except capacity, listed size, single-unit price and the UN38.3 note.
- VEMD8080: pad layout and anode pad from the Vishay drawing; USD price breaks.
- VLMS1500-GS08 and SFH 4053: DigiKey stock and price; lifecycle flag.
- Mill-Max 0914: plunger and body diameter, current rating, price.
- USB4105-GF-A: body dimensions, price at 100 and 1000, maker HQ.
- Watch crystal: tolerance; price of size 28.0.
- McMaster 1598K16: part number and price.
- Gore VE80205: water entry pressure, IP rating, hole size, US source.
- PCB: via plugging at Sierra and Bay Area Circuits; quick-turn tiers at Summit; Screaming Circuits and CircuitHub capability.
- MJF: Protolabs tolerance; Xometry US-made option; other US bureaus.

## 5. Sources seen

Local files:

- L1. `/usr/share/kicad/footprints/Connector_FFC-FPC.pretty/` (Hirose_FH12-10S-0.5SH, Molex_54548-1071, TE_1-1734839-0 footprints)
- L2. `/usr/share/kicad/footprints/Connector_USB.pretty/USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal.kicad_mod`; `/usr/share/kicad/symbols/Connector.kicad_sym`
- L3. `/usr/share/kicad/footprints/OptoDevice.pretty/`, `/usr/share/kicad/footprints/LED_SMD.pretty/`

Public repository files (secondary sources):

- G1. https://raw.githubusercontent.com/fearedspark/digital-level/HEAD/Hardware/project_lib.pretty/LS013B7DH03.kicad_mod and https://raw.githubusercontent.com/fearedspark/digital-level/HEAD/Hardware/project_lib.kicad_sym
- G2. https://raw.githubusercontent.com/samp38/varioSmooth/HEAD/v2/pcb/kicad/varioSmooth_ext/varioSmooth_ext.kicad_sch
- G3. https://raw.githubusercontent.com/captainchapster/Eigentime32/HEAD/hardware/lcd.kicad_sch
- G4. https://raw.githubusercontent.com/TUDSSL/FreeBie/HEAD/Hardware/design/rev4/display.kicad_sch
- G5. https://raw.githubusercontent.com/alx-alexpark/watch/HEAD/pcb/display.kicad_sch
- G6. https://raw.githubusercontent.com/esl-epfl/VersaSens/HEAD/VersaSens_HW/symbols/SamacSys_Parts.pretty/VEMD8080.kicad_mod and https://raw.githubusercontent.com/esl-epfl/VersaSens/HEAD/VersaSens_HW/symbols/SamacSys_Parts.kicad_sym
- G7. https://raw.githubusercontent.com/Kampi/KiCad/HEAD/Footprints/Vishay.pretty/VEMD808x.kicad_mod
- G8. https://raw.githubusercontent.com/Philippe12/HorseSense/HEAD/lib/footprints.pretty/XDCR_VEMD8080.kicad_mod
- G9. https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/main/boards/shields/ls0xx_generic/doc/index.rst

Web pages (text seen through search extracts):

- W1. https://cdn.sparkfun.com/assets/d/e/8/9/7/LS013B7DH03_datasheet.pdf
- W2. https://www.digikey.com/en/products/detail/sharp-microelectronics/LS013B7DH03/425-2903-ND/5300387 (and regional copies: digikey.jp, digikey.tw, digikey.fi, digikey.be, digikey.ie)
- W3. https://www.mouser.com/datasheet/2/365/LS013B7DH03%20SPEC_SMA-224806.pdf ; https://www.azumotech.com/uploads/2020/02/LS013B7DH03_Spec.pdf ; https://media.digikey.com/pdf/Data%20Sheets/Sharp%20PDFs/LS013B7DH03_Spec.pdf
- W4. https://www1.futureelectronics.com/doc/Sharp/LS013B7DH03.pdf ; https://www.panelook.com/upload/201709/LS013B7DH03_LCP-2111042_20111019_201709064347.pdf
- W5. https://datasheet.octopart.com/LS013B7DH03-Sharp-Microelectronics-datasheet-23806624.pdf
- W6. https://datasheets.ibselectronics.com/LS013B7DH01-Sharp-Microelectronics-datasheet-27690001.pdf ; https://www.mouser.com/ds/2/365/Sharp_Memory_LCD_Brochure_2015-746065.pdf
- W7. https://www.futureelectronics.com/p/6117773 ; https://www.edinventory.com/parts/ls013b7dh03_sharp-devices-europe
- W8. https://www.mouser.com/ProductDetail/Sharp-Microelectronics/LS013B7DH03?qs=La0%2B8xZSm19d3Mbp4mkNrQ%3D%3D
- W9. https://www.arrow.com/en/products/ls013b7dh03/sharp ; https://octopart.com/part/sharp/LS013B7DH03
- W10. https://www.beyondinfinite.com/lcd/Library/Sharp/LS013B7DH03.pdf ; https://datasheet4u.com/datasheets/Sharp/LS013B7DH03/1110396 (with W3, W4, W5)
- W11. https://www.digikey.hk/en/products/detail/molex/0545481071/3196999 ; https://sg.element14.com/molex/54548-1071/connector-ffc-fpc-10pos-1row-0/dp/3107453 ; https://www.molex.com/en-us/products/part-detail/545481071 ; https://octopart.com/part/molex/54548-1071
- W12. https://www.digikey.com.au/en/products/detail/molex/0545481072/16629956 ; https://www.digikey.co.za/en/products/detail/molex/0545481072/16629956 ; https://www.digikey.fr/en/products/detail/molex/0545481072/16629956
- W13. https://digikey.cn/en/products/detail/te-connectivity-amp-connectors/1-1734839-0/1860466 ; https://octopart.com/part/te-connectivity/1-1734839-0 ; https://www.te.com.cn/chn-zh/product-1-1734839-0.datasheet.pdf ; https://futureelectronics.com/p/interconnect--ffc-fpc--ffc-fpc-connectors/1-1734839-0-te-connectivity-4108672
- W14. https://www.digikey.tw/en/products/detail/hirose-electric-co-ltd/FH12-10S-0-5SH-55/1110314 ; https://www.digikey.co.za/en/products/detail/hirose-electric-co-ltd/FH12-10S-0-5SH-55/1110314 ; https://futureelectronics.com/p/8267957 ; https://www.digikey.jp/en/products/detail/hirose-electric-co-ltd/FH12A-10S-0-5SH-55/1110331
- W15. https://www.edmundoptics.com/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392/ ; https://www.edmundoptics.cn/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392/ ; https://www.3doptix.com/catalog/optics/prism/edmund-optics/32-526 ; https://edmundoptics.com.au/p/2mm-aluminum-amp-mgfsub2sub-coated-n-bk7-right-angle-prism/5855
- W16. https://www.gophotonics.com/products/prisms/tower-optical-corporation/34-293-mpu-2-0 ; https://gophotonics.com/products/prisms/tower-optical-corporation/34-293-mpch-0-7 ; https://findlight.net/company/tower-optical-corporation/optics/prisms ; https://www.edmundoptics.com/p/2mm-alum-amp-ar-coated-n-sf11-micro-right-angle-prism/8131/
- W17. https://www.powerstream.com/li-pol.htm ; https://www.powerstream.com/wp/li-pol/
- W18. https://www.powerstream.com/thin-lithium-ion.htm ; http://www.powerstream.com/wp/thin-lithium-ion
- W19. https://cmbatteries.com/?p=22753 ; https://sparkfun.com/products/13813 ; https://www.dnkpower.com/3-7v-240mah-lipo-battery/
- W20. https://www.radiolocman.com/datasheet/data.html?di=503537 ; https://www.vishay.com/en/product/84565/ ; https://www.digikey.ca/en/products/detail/vishay-semiconductor-opto-division/VEMD8080/8602378 ; https://lcsc.com/product-detail/Infrared-Receivers_Vishay-Intertech-VEMD8080_C511402.html
- W21. https://octopart.com/part/vishay/VLMS1500-GS08 ; https://www.datasheets.com/vishay/vlms1500-gs08 ; https://datasheet.chipsmall.com/VLMG1500-GS08/136693.pdf ; https://findchips.com/detail/vlms1500-gs08/Vishay-Semiconductors?f=dsa ; https://za.rs-online.com/web/p/leds/1656154 ; https://www.farnell.com/datasheets/1809983.pdf
- W22. https://media.distrelec.com/Web/Downloads/_t/ds/SFH_4053_eng_tds.pdf ; https://www.digikey.nl/en/products/detail/ams-osram-usa-inc/SFH-4053/2713572 ; https://ie.farnell.com/osram-opto-semiconductors/sfh-4053/infrared-emitter-860-nm-smd/dp/2981755 ; https://www.cytechsystems.com/en/product/sfh-4053 ; https://au.rs-online.com/web/p/ir-leds/7350585/ ; https://ams-osram.com/ja/products/leds/ir-leds/osram-chip-led-sfh-4053b
- W23. https://www.digikey.ca/en/products/detail/mill-max-manufacturing-corp/0906-0-15-20-76-14-11-0/1147048 ; https://il.farnell.com/mill-max/0906-0-15-20-76-14-11-0/spring-loaded-contact-pin-5-24mm/dp/2668369 ; https://futureelectronics.com/p/interconnect--connectors-pcb--pcb-pins-and-receptacles/0906-0-15-20-76-14-11-0-mill-max-7001062 ; https://azcus.digikey.com/en/products/detail/mill-max-manufacturing-corp/0906-8-15-20-76-14-11-0/3737528
- W24. https://www.mill-max.com/sites/default/files/external/catalog/2021-01/023-028.pdf ; https://www.mouser.com/new/mill-max/millmax085/
- W25. https://www.mouser.jp/mill-max-0914-Series ; https://www.digikey.co.uk/en/products/detail/mill-max-manufacturing-corp/0914-0-15-20-77-14-11-0/1147053 ; https://au.element14.com/mill-max/0914-0-15-20-77-14-11-0/connector-type-spring-probe/dp/1654368 ; https://cn.element14.com/en-CN/mill-max/0914-0-15-20-77-14-11-0/connector-spring-contact/dp/1654368
- W26. https://www.findchips.com/search/USB4105-GF-A ; https://www.digikey.sg/en/products/detail/gct/USB4105-GF-A/11198510
- W27. https://www.esslinger.com/watch-crystal-flat-round-standard-mineral-glass-crystal-1mm-thick/ ; https://www.esslinger.com/watch-glass-round-flat-mineral-glass-crystals-1mm-thick.aspx ; https://www.julesborel.com/s.nl/it.A/id.12462/.f
- W28. https://www.mcmaster.com/products/balls/diameter~1-mm/
- W29. https://multimedia.3m.com/mws/media/1235572O/uv-primer-technical-data-sheet-canada-english-pdf.pdf ; https://tbpconverting.com/wp-content/uploads/2022/02/PDS-3M-5906-5907-5908-5909-TBP-Converting.pdf ; https://www.digikey.co.uk/en/product-highlight/3/3m/thin-vhb-tapes-5906-5907-5908-5909-and-5915
- W30. https://www.3mcanada.ca/3M/en_CA/p/d/b40071697/ ; https://www.digikey.ca/en/products/detail/3m-tc/468MP-1-5/2649266 ; https://www.digikey.ca/en/products/detail/3m-tc/468MP-4-5/2658179 ; https://azcus.digikey.com/en/products/detail/3m-tc/468MPSQ-12-6/2649265
- W31. https://gore.com/system/files/2024-07/gore-ptv-adhesive-serie-datasheet-en.pdf ; https://www.gore.com/products/venting/adhesive-vents
- W32. https://octopart.com/part/gore/VE80205 ; https://uk.rs-online.com/web/p/enclosure-ventilation/2879532?gb=s ; https://se.rs-online.com/web/p/enclosure-ventilation/2879532 ; https://www.gore.com/system/files/2024-07/GOR202011_GS_Factsheet_20240117.pdf ; https://news.thomasnet.com/fullstory/protective-vent-targets-small-electronic-displays-20000192/
- W33. https://www.advancedpcb.com/en-us/resources/manufacturing-capabilities/ ; https://4pcb.com/expanded-capabilities.html ; https://www.4pcb.com/custom-pcb.html
- W34. https://www.advancedpcb.com/getmedia/68280c59-ac23-43ab-8163-8365cf127d5e/CorpManCapabilities6-19-2023.pdf
- W35. https://www.protoexpress.com/products/sierra-standard-product/ ; https://www.protoexpress.com/faq/hdi-pcbs/ ; https://www.protoexpress.com/pcb/hdi-pcb-manufacturing-capabilities/ ; https://www.protoexpress.com/products/microelectronics-pcb/
- W36. https://bayareacircuits.com/wp-content/uploads/2025/12/capabilities.pdf ; https://bayareacircuits.com/pcb-capabilities/
- W37. https://www.royalcircuits.com/board-specifications/ ; https://www.royalcircuits.com/rigid-pcb-capabilities/ ; https://summitinterconnect.com/capabilities-fabrication/ ; https://summitinterconnect.com/technology/
- W38. https://docs.oshpark.com/services/four-layer ; https://docs.oshpark.com/services/four-layer-medium-run ; https://docs.oshpark.com/services/two-layer-hhdc ; https://oshpark.com/pricing
- W39. https://www.macrofab.com/pcba/ ; https://advancedpcb.com/en-us/solutions/pcb-assembly/
- W40. https://www.protolabs.com/en-gb/resources/blog/designing-a-part-for-multi-jet-fusion/ ; https://www.protolabs.com/resources/design-tips/how-to-use-multi-jet-fusion-for-functional-3d-printed-parts/ ; https://rapidmade.com/mjf-best-practices-and-common-mistakes/
- W41. https://xometry.uk/?p=57281 ; https://xometry.pro/wp-content/uploads/2024/05/EN-EU-MJF-Design-Guide.pdf ; https://www.wevolver.com/article/multi-jet-fusion-mjf-3d-printing-technology-overview
- W42. https://www.protolabs.com/services/3d-printing/vapor-smoothing/ ; https://fictiv.com/finishes/vapor-smoothing ; https://hubs.com/surface-finishing-services/vapor-smoothing-services ; https://www.wevolver.com/article/vapour-smoothing-an-effective-surface-finish-process-in-3d-printing
