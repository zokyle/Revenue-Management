# GreenLine GL-1: where to buy every part in the US (sourcing report)

Design revision: D-EVT1. Date of every check: 2026-11-11. Companion file: `sourcing.csv` (the same lines, machine-readable).
Report revision 2, the same day, after two independent reviews. What the reviews changed is marked in the text; facts taken
from a review and not re-checked are worded "reported in review" (section 2).

> **Nothing in this project has been built or tested.** This is a buying study done on paper. No order was placed, no quote was
> requested, no sample was handled. Every price is a budget figure, not an offer.

## 1. One-page summary

**VERIFIED** means a US source was seen *listing* the exact item in a web-search result on 2026-11-11. It does not mean
the item was on the shelf. **PROVISIONAL** means no such listing was seen, or the item is not chosen yet. Section 2 gives
the full definitions and the limits of the evidence.

### 1.1 Scoreboard

| Measure | Result |
|---|---|
| Lines in the bill of materials (parts, material classes and outside services) | **64** |
| Lines for which a US source was seen listing the item (VERIFIED) | **36 of 64 (56 %)** |
| Of those, lines that showed zero stock on the US page at the snapshot | **2**: the display and the tilt sensor. "Listed" is not "on the shelf" |
| Lines still PROVISIONAL | 28 (9 of them are adhesives that the design has not chosen yet) |
| Share of the 10-unit cost that sits on VERIFIED lines | **84 %** (USD 727 of 865 per marker plus cradle) |
| Share of the 10-unit cost that rests on a price actually seen | **26 %**. The rest is assumed, reported but unverified, or needs a quote |
| Budget, one marker plus one cradle, at 10 units | about **USD 865** in parts and outside services, before fixtures, test fees and labour. This prices ten finished FR-4 markers and ten consumer cradles, and nothing else |
| Budget, the whole EVT programme of the other two plans (section 10.5) | about **USD 16,100** in parts and outside services, about 1.8 times the ten-unit order. It covers parts for 15 builds, 25 assembled boards, 20 test shells, both kinds of base plate and 12 cradles. Only 16 % of it rests on a price seen |
| Budget, one marker plus one cradle, at 1000 units | about **USD 134**, before final-assembly labour, test, scrap and tooling. Range for the marker alone: USD 94 to 241, set almost entirely by the price of the prisms |

```
Lines VERIFIED (listed)   [#################.............]  36 of 64
Cost on VERIFIED lines    [#########################.....]  84 % (10-unit build)
Cost from a seen price    [########......................]  26 % (10-unit build)
```

How the lines split:

| Group | Lines | VERIFIED | PROVISIONAL |
|---|---|---|---|
| Electronic parts, marker | 22 | 20 | 2 |
| Electronic parts, cradle | 4 | 2 | 2 |
| Mechanical purchased parts | 9 | 3 | 6 |
| Tapes and foam | 6 | 2 | 4 |
| Adhesives (by class; none is selected) | 9 | 0 | 9 |
| Custom parts and outside services | 14 | 9 | 5 |
| **All** | **64** | **36** | **28** |

What this says in one sentence: **almost every catalogue part has a US seller, but only about 26 % of the money
in a small build is backed by a price that was seen**, because the big-ticket items (bare board, board assembly, die cutting,
printing) are priced by quotation, and nine adhesives are still classes rather than products.

### 1.2 The three biggest supply risks, and what to do about each

| # | Risk | Why it matters | What to do |
|---|---|---|---|
| 1 | **Camera cube OVM7692-RYAA** (2 per marker) | One maker and one US distributor (DigiKey, with a 20-week lead time behind its stock). Nothing else drops into its place: the camera bay, the prism height and the light hoods are all built round this cube. It is an old phone-era design. No end-of-life notice was found, but one sibling variant is already listed obsolete. Its pad map is still not public. | (a) Register with OmniVision for the datasheet now. (b) Buy the cubes for the first two builds (about 150) as soon as a live page shows stock. (c) For production, **one factory reel is 2,500 cubes, more than 1000 markers need**: a single lifetime buy of roughly USD 11,000 to 16,000 removes the risk. |
| 2 | **Sharp LS013B7DH03 display** | One maker, no drop-in second source. The DigiKey US page showed **0 in stock and a 28-week lead time**; Future, Arrow and Avnet showed zero. Sharp is closing LCD plants, although a distributor says its memory-display technology continues. A Sharp change notice for this display family reports a new glass supplier and, for some models, a new glass thickness. Whether it touches this part is not confirmed (PROVISIONAL). | (a) Buy the panels for the first two builds (60 to 70, about USD 9 each) the day a live page shows stock. (b) Get the change notice and the current drawing; measure the delivered lot. (c) For production, order seven months ahead, or buy the run outright (about USD 6,300 to 6,800 per 1000). |
| 3 | **Lithium-polymer cell, 2 x 10 x 30 mm, with protection board** | One US seller (PowerStream, Utah). No second US source in this size was found: every other small protected cell seen is thicker or wider than the bay. No stock figure, volume price, safety certificate, protection data or drawing was seen. The one price seen (USD 12.00 at 1) may come from a listing dated 2024 (reported in review, unconfirmed). | (a) Ask PowerStream now for the datasheet, drawing, protection data, UN 38.3 summary, IEC 62133-2 or UL 1642 status, lead time and prices at 10, 100 and 1000. (b) Buy 20 to 30 cells and measure them. (c) Do not count on the same seller's PGEB021235 (2 x 12 x 35 mm) as a fallback: it does not fit this board, and the bay cannot simply be opened up (section 12, item 16). A fallback cell means a new board layout or a custom cell. Ask a second maker to quote a custom cell of the present size. |

Section 9 gives the evidence behind each row. The quantities assume the EVT programme of section 10.5 (about 25 assembled
boards) and a second build of about 50 markers.

### 1.3 Other findings that need a decision

1. **The infrared grain LED is being discontinued.** DigiKey lists the ams OSRAM SFH 4053 as *Last Time Buy*, last buy date
   31 Jan 2027. It is fine for EVT. Pick a replacement before production. First choice: the same maker's newer SFH 4053B,
   reported as the successor named in the maker's notice (PROVISIONAL: confirm the footprint and find a US distributor).
   Parts from other makers give less light (Inolux IN-S42CTQIR is Active and stocked; 5.5 against 7 mW/sr).
2. **The battery temperature sensor is "not recommended for new designs".** Murata's notice names the successor
   NCU15XH103F60RC and plans the last order for March 2032. Change the part number now, while it costs nothing.
3. **Two prisms cost about USD 189 per marker at 10 units**, 22 % of the whole small-build cost. No published
   volume price for a 2.0 mm aluminised prism was found. That one quote moves a 1000-unit marker between about
   USD 94 and about USD 241 in parts and services.
4. **No US distributor was found for the Gore VE80205 vent**, and its water-entry pressure is still unconfirmed. Ask Gore
   directly, or evaluate a Porex vent disc of the same 5 x 2 mm size.
5. **Production cover glass: 1.0 mm may not be a stocked thickness** of chemically strengthened glass. The one US fabricator
   checked listed 0.8 and 1.1 mm, not 1.0 mm, in a release that a review dates to 2020; its later lists are reported to
   differ. Ask it what it stocks near 1.0 mm today. The recess leaves 0.12 mm; a 1.1 mm glass would leave 0.02 mm.
6. **Nine adhesives and three tapes are still classes, not products.** Real candidates are named in section 7. None is proven on
   vapor-smoothed nylon or on solder mask. No black wicking sealant for the cover-glass rim was found at all.
7. **The fine-line rule is quoted two ways** (0.10 mm in the design specification, 0.09 mm in the layout tool), and 0.100 mm is
   a hair under the "4 mil" (0.1016 mm) that the fabricators publish as their standard tier. See section 12.
8. **The ten-unit budget is for ten bare units.** The EVT programme in `MANUFACTURING_PLAN.md` and `VALIDATION_PLAN.md`
   needs about 1.8 times as much in parts and outside services (section 10.5). Four of the ten units use a printed
   PA12 base plate; that plate now has its own line in section 8.
9. **The tape named for fixing the cell is thicker than its own limit** (about 0.058 mm against the 0.05 mm in the YAML).
   Relax the limit or find a thinner tape (section 6).

### 1.4 Suggested buying order

1. Send the three information requests that cost nothing: OmniVision (datasheet), PowerStream (cell data and prices), Sharp or
   its distributor (change notice and drawing).
2. Buy the long-lead, single-source parts for the first two builds together: camera cubes, displays, tilt sensors, cells.
   Add the flash memory: a factory lead time of a year or more is reported at one distributor (PROVISIONAL).
3. Request quotes on the same day for: bare boards, board assembly, base plates, printing, die cutting, window glass, prisms in volume.
4. Order adhesive candidates and run the coupon tests in `mechanical/README.md` section 9 before choosing.
5. Order the remaining catalogue parts (they are stocked in depth) only when the board layout is final.

---

## 2. How to read this report

A **bill of materials** (BOM) is the ingredient list of the product: every part and every outside service needed to make one
marker and one charging cradle. This report goes down that list and asks one question per line: *can it be bought in the US today,
from whom, and at what risk?*

| Term | Plain meaning |
|---|---|
| US-sourceable | Can be ordered from a US distributor, US manufacturer or US service bureau and shipped from the US to a US address, with no import step for the buyer. It does **not** mean "made in USA". Where the country of manufacture was learned it is stated; where it was not, the table says "not found". |
| VERIFIED | A US source for this exact item (or a US vendor publishing this exact capability) was seen in a web-search result on 2026-11-11, by this study or by the research files in `docs/research/` written the same day. The source and URL are given. VERIFIED means listed. It does not mean in stock. |
| PROVISIONAL | Everything else: the fact comes from memory, the search found nothing, or the item has not been chosen yet. It must be confirmed before ordering. |
| Lead time | How long the factory takes to deliver when the distributor's shelf is empty. A 28-week lead time is half a year of waiting. |
| Lifecycle | Where a part is in its life, like a car model: *Active* (in the showroom), *not recommended for new designs* (still built, successor announced), *last-time buy* (final orders by a set date), *obsolete* (gone). |
| Single source | Only one company makes it. Like a town with one bridge: fine until the bridge closes. |
| Quote | No price is published. The supplier prices the job after seeing the drawing. |
| EVT, DVT | Engineering validation test: the first small build, about 10 units. Design validation test: the second, larger build that follows it. |

**Limits of the evidence. Please read once.**

- Supplier web pages could not be opened from this session (the hosts are outside the session's allowed network). All web evidence is
  the text that the search tool returned from those pages. It is an extract of unknown date, not the live page.
- Distributor stock and price figures are snapshots. Several come from regional copies of a DigiKey page (Canada, Europe, Asia) or
  from price aggregators, and they often disagree with each other. Each figure names where it was seen.
- A VERIFIED line therefore means "a US source exists and lists it". It does not promise that the part is on the shelf today.
  Open the live page before you order.
- **Reported in review.** Two independent reviews of this report ran their own searches the same day. This revision could
  not repeat them: the session's search allowance was used up, and vendor pages cannot be opened. Where a review
  contradicted or added to this report, the text says "reported in review" and the point is **PROVISIONAL** until someone
  opens the page. Section 13 lists those sources separately.
- Hosts that would need to be allowed for a live check: `www.digikey.com`, `www.mouser.com`, `www.powerstream.com`, `www.ovt.com`,
  `www.edmundoptics.com`, `www.mcmaster.com`, `www.gore.com`, `www.3m.com`, `www.protolabs.com`, `bayareacircuits.com`,
  `www.protoexpress.com`, `www.findchips.com`, `www.futureelectronics.com`, `ams-osram.com`, `www.knightoptical.com`,
  `www.porex.com`.

---

## 3. Electronic parts on the marker

Prices are USD per piece. "not seen" means no US-dollar price at that quantity appeared in any search result; the notes under the
table give the nearest price that was seen.

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Microcontroller | STM32U585RIT6 | The single processor: runs the cameras, tilt sensor, display, USB and the putt maths | [DigiKey (497-STM32U585RIT6-ND); Future Electronics](https://www.digikey.ca/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579) | not seen / not seen | DigiKey regional snapshots 222 to 1,497 pcs (US page not seen); lead time 13 weeks. Future: 0 in stock | low: current ST family, several distributors, tray of 160 | STM32U575RIT6 (same package; pin compatibility from memory, PROVISIONAL) | **VERIFIED** 2026-11-11 |
| Camera cube (2 per marker) | OVM7692-RYAA | The two forward-looking eyes (640 x 480 pixels each) | [DigiKey (884-1027-1-ND)](https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RYAA/3516559) | not seen / not seen | 6,282 at DigiKey, minimum order 1, lead time 20 weeks (aggregator copy, undated). Hotenda: 0 in stock, 14-week factory lead | high: one maker, no drop-in alternative, an old phone-era design (launch about 2010, from memory), 20-week lead, full datasheet only under registration | none that drops in. OVM7692-RAAA is a different size (2.815 x 3.179 x 2.60 mm) | **VERIFIED** 2026-11-11 |
| Tilt and motion sensor (IMU) | LSM6DSV16XTR | Measures the slope under the marker and wakes it when it is moved | [DigiKey (497-LSM6DSV16XTRCT-ND); Mouser (511-LSM6DSV16XTR)](https://www.digikey.com/en/products/detail/stmicroelectronics/LSM6DSV16XTR/16841908) | not seen / 3.06 | DigiKey US page: 0 in stock, with a purchase limit (snapshot). Mouser (India page): 1,370 in stock, 5,000 on order, factory lead time 24 weeks | medium: one maker, zero at DigiKey US at the snapshot, 24-week factory lead | ST LSM6DSV or LSM6DSO family in the same LGA-14 package (PROVISIONAL, from memory; the firmware driver would change) | **VERIFIED** 2026-11-11 |
| Display (memory LCD, 1.28 inch, 128 x 128) | LS013B7DH03 | Shows the aim line; readable in sunlight; uses almost no power | [DigiKey (425-2903-ND); Future Electronics; Arrow](https://www.digikey.com/en/products/detail/sharp-microelectronics/LS013B7DH03/425-2903-ND/5300387) | 8.82 / not seen | DigiKey US page snapshot: 0 in stock, manufacturer lead time 28 weeks. Other DigiKey regional snapshots: 613 to 11,356. Future, Arrow, Avnet: 0 | high: one maker, no drop-in second source, 28-week lead, zero at US distributors at the snapshot, Sharp is closing LCD plants | none that drops in. JDI LPM013M126A (1.28 inch, 176 x 176 colour) has a different outline and no US distributor listing was found | **VERIFIED** 2026-11-11 |
| Display connector (10-way, 0.5 mm pitch, top contact) | FH12A-10S-0.5SH(55) | Socket that the display's flexible tail plugs into | [DigiKey (HFK110CT-ND); Mouser; Future Electronics](https://www.digikey.jp/en/products/detail/hirose-electric-co-ltd/FH12A-10S-0-5SH-55/1110331) | not seen / not seen | DigiKey: 13,536 on cut tape and 10,736 on Digi-Reel (aggregator copy); lead time 12 weeks | low | Molex 54550-1071 class or SMK CFP-4510-0150F (Sharp's own recommendation); neither checked for footprint | **VERIFIED** 2026-11-11 |
| Flash memory (64 Mbit) | MX25R6435FZNIL0 | Stores logged camera frames, calibration and settings | [DigiKey](https://www.digikey.com/en/products/detail/macronix/MX25R6435FZNIL0/6558605) | not seen / 2.13 | Conflicting snapshots: 12,304 (ES), 62,321 (UK), 0 (IT, IE); one US-page extract said backorders were not accepted because of constrained supply. Reported in review, not re-checked: 65,732 on the DigiKey US page with a 30-day purchase cap; Future shows a factory lead time of 52 weeks or more and no factory stock | medium to high: stock snapshots conflict, one extract reports constrained supply, and a second distributor is reported to quote a factory lead time of a year or more (PROVISIONAL) | Winbond W25Q64JV in WSON 6 x 5 (PROVISIONAL, not searched; its 2.7 V minimum supply is tight on a 2.8 V rail) | **VERIFIED** 2026-11-11 |
| Battery charger chip | MCP73831T-2ACI/OT | Charges the cell at 20 mA from the cradle | [DigiKey (MCP73831T-2ACI/OTCT-ND)](https://www.digikey.ca/en/products/detail/microchip-technology/MCP73831T-2ACI-OT/964301) | not seen / not seen | DigiKey CA page: 50,036 (earlier snapshot); AU and UK pages: out of stock; lead time 4 weeks | low | Microchip MCP73832T-2ACI/OT (same family; PROVISIONAL) | **VERIFIED** 2026-11-11 |
| Always-on 2.8 V regulator | MCP1700T-2802E/TT | Feeds the processor, tilt sensor and display with very little standby drain | [DigiKey](https://www.digikey.co.za/en/products/detail/microchip-technology/MCP1700T-2802E-TT/5148837) | not seen / not seen | DigiKey ZA page: 15,084 in stock; lead time 5 weeks; an aggregator shows 9,000 | low | Microchip MCP1702T-2802E/CB or TI TPS7A02 2.8 V (PROVISIONAL; different package) | **VERIFIED** 2026-11-11 |
| 3.3 V regulator for the USB supply pin | MCP1700T-3302E/TT | Powers the processor's USB pin; only live in the cradle | [DigiKey](https://www.digikey.ca/en/products/detail/microchip-technology/MCP1700T-3302E-TT/652676) | not seen / not seen | DigiKey: 33,458 (CA), about 31,800 (ES), 0 (DE punch-out page); Findchips shows 26,542 on reel, 7-week lead | low | any 3.3 V SOT-23 LDO with the same pin order (PROVISIONAL) | **VERIFIED** 2026-11-11 |
| Switchable 2.8 V regulator for the cameras | LP5907MFX-2.8/NOPB | Low-noise supply that is switched on only during a read | [DigiKey](https://www.digikey.com/es/products/detail/texas-instruments/LP5907MFX-2-8-NOPB/3906436) | 0.402 / not seen | DigiKey: 23,519 and 45,920 on two USD pages (snapshots) | low | other pin-compatible 2.8 V SOT-23-5 LDOs (PROVISIONAL) | **VERIFIED** 2026-11-11 |
| USB static-discharge protection | USBLC6-2SC6 | Protects the USB and power contacts from static shocks | [DigiKey (497-5235-1-ND)](https://www.digikey.co.uk/en/products/detail/stmicroelectronics/USBLC6-2SC6/1121688) | not seen / 0.114 | 156,665 (Findchips copy of DigiKey); 25-week lead time | low | equivalent SOT-23-6 USB ESD arrays from other makers (PROVISIONAL) | **VERIFIED** 2026-11-11 |
| 32.768 kHz crystal (6 pF) | ABS07-120-32.768KHZ-T | Keeps time and paces the display refresh while the marker sleeps | [DigiKey](https://www.digikey.ca/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043) | not seen / 0.45 | 110,303 (UK page), 90,489 (CA page); lead time 14 weeks | low | another 3.2 x 1.5 mm, 6 pF watch crystal (PROVISIONAL) | **VERIFIED** 2026-11-11 |
| Photodiode (grain reader) | VEMD8080 | Light sensor of the experimental grain reader | [DigiKey](https://azcus.digikey.com/en/products/detail/vishay-semiconductor-opto-division/VEMD8080/8602378) | not seen / not seen | DigiKey regional snapshots 3,777 to 4,541; lead time 9 to 16 weeks | low | Vishay VEMD8081 (sister part listed at DigiKey; fit not checked) | **VERIFIED** 2026-11-11 |
| Red LEDs, 0402 (8 per marker) | VLMS1500-GS08 | Red lights of the grain reader | [DigiKey; Mouser (78-VLMS1500-GS08)](https://www.findchips.com/search/vlms1500-gs08) | not seen / not seen | Aggregator: DigiKey about 2,393 (12-week lead), Mouser about 57,437 | low: common part with same-size alternatives | Kingbright APHHS1005SURCK (DigiKey 754-1104; 0 in stock on the CA and ES pages at the snapshot) | **VERIFIED** 2026-11-11 |
| Near-infrared LEDs, 0402 (8 per marker) | SFH 4053 | Infrared lights of the grain reader | [DigiKey (product 2713572)](https://www.digikey.com.mx/en/products/detail/ams-osram-usa-inc/SFH-4053/2713572) | not seen / 0.24 | DigiKey regional snapshots 135 to 22,390; status Last Time Buy, last buy date 31 Jan 2027 | high for production: the maker is discontinuing it (last-time-buy date 31 Jan 2027; last delivery reported as 31 Jan 2028, not re-checked). Fine for EVT | First choice: ams OSRAM SFH 4053B, the same maker's newer version (seen on the maker's site in bom-verification-opto.md; reported in review as the replacement named in the maker's discontinuation notice; no US distributor stock found: PROVISIONAL). Second choices, all weaker emitters: Inolux IN-S42CTQIR (850 nm, 0402, Active, 15,429 to 33,249 at DigiKey regional pages; 5.5 mW/sr); Wurth 15404085BA420 (3 mW/sr reported); Rohm SML-P14RWT86 (860 nm; 1.8 mW/sr at 50 mA reported) | **VERIFIED** 2026-11-11 |
| 220 ohm resistor arrays, 4-in-1 (6 per marker) | EXB-28V221JX | Protect the camera wires that the two cameras share | [DigiKey (Y7221CT-ND); Arrow; Future Electronics](https://www.digikey.com.au/en/products/detail/panasonic-electronic-components/EXB-28V221JX/256279) | not seen / not seen | DigiKey AU page: 72,722; MX punch-out page: 0; lead time 18 weeks | low | Yageo YC124 or Bourns CAT16 class 0804 array (PROVISIONAL, not searched) | **VERIFIED** 2026-11-11 |
| Small N-channel MOSFET | BSS138LT1G | Lets the firmware stop charging when the cell is too hot or too cold | [DigiKey](https://www.digikey.com/en/products/detail/onsemi/BSS138LT1G/918376) | not seen / 0.0734 | DigiKey US: 18,220 in stock plus 207,900 marketplace stock (snapshot) | low | Nexperia BSS138BK or Diodes BSS138-7-F (PROVISIONAL; check the 1.5 V maximum gate threshold) | **VERIFIED** 2026-11-11 |
| Schottky diode, 30 V 0.5 A | B0530WS-7-F | One-way valve between the cradle contact and the charger | [DigiKey (B0530WS-FDICT-ND)](https://azcus.digikey.com/en/products/detail/diodes-incorporated/B0530WS-7-F/816548) | not seen / 0.074 | About 108,418 (Findchips copy of DigiKey); 40-week lead time | low | onsemi NSR0530HT1G (higher forward voltage) | **VERIFIED** 2026-11-11 |
| Temperature sensor (10 kohm NTC, 0402) | NCP15XH103F03RC | Sits beside the cell and decides whether charging is allowed | [DigiKey (490-4801-1-ND)](https://www.digikey.com/en/products/detail/murata-electronics/NCP15XH103F03RC/1644666) | 0.09 / not seen | DigiKey US/MX page: about 77,250 in stock; NL page: 0; Future: 10-week factory lead | medium: flagged 'not recommended for new design'; Murata names a successor and plans the last order for March 2032 | Murata NCU15XH103F60RC (the successor named in Murata's notice; confirm the B constant) | **VERIFIED** 2026-11-11 |
| Lithium-polymer cell with protection board, 2 x 10 x 30 mm | GM201030-PCB | The rechargeable battery (listed at 43 mAh) | [PowerStream Technology, Orem, Utah (direct)](https://www.powerstream.com/li-pol.htm) | not seen / not seen | Not shown. PowerStream says some cells are stocked in Utah, quotes 3 to 6 weeks on a sister page, and warns of ocean freight from China for large quantities. Reported in review: the listing page may carry a date of 27 September 2024 (one extract; a second search did not confirm it) | high: one seller, no second US source in this size, no certificates or protection data seen | No fit-compatible US alternative found. PowerStream PGEB021235-PCB (2 x 12 x 35 mm, 40 mAh) is 2 mm wider than the bay and, with the allowance the bay makes for the protection board, about 5 mm longer: it does not fit this board (section 12, item 16) | **VERIFIED** 2026-11-11 |
| Chip resistors, 0402 (about 30 per marker) | class: 68R x5, 33R, 1k x2, 2.2k x2, 10R, 10k, 10.0k 1 %, 49.9k 1 %, 100k (several), 470k, 1M x4 and similar | Set currents and voltage levels all over the board | DigiKey, Mouser, Arrow or Newark (commodity; not checked line by line) | not seen / not seen | commodity; not checked | low | any equivalent 0402 thick-film part | **PROVISIONAL** (not searched) |
| Ceramic chip capacitors, 0402 / 0603 (about 32 per marker) | class: 100 nF, 1 uF, 4.7 uF, 10 nF, 10 pF, crystal load capacitors | Smooth the supplies and set timing | DigiKey, Mouser, Arrow or Newark (commodity; not checked line by line) | not seen / not seen | commodity; not checked | low | any equivalent X5R / X7R / C0G part of the same value and voltage | **PROVISIONAL** (not searched) |

Country of manufacture: not found for the lines above, except: Lithium-polymer cell with protection board, 2 x 10 x 30 mm: China (cell maker reported as GM Battery in power.md; unverified).

Notes on these lines:

- **Microcontroller**: Prices seen: EUR 6.30 at 10 and EUR 5.36 at 100 (DigiKey AT); CAD 9.11 at 960 (DigiKey CA); USD 4.83 at 160+ (Future). No USD price at 10 or 1000 seen. Do not order the -Q suffix part (different pinout).
- **Camera cube (2 per marker)**: DigiKey price shown only as a range, USD 6.25 to 44.95 (Findchips). Prices seen at non-US sellers: LCSC 11.45 at 1, 4.42 at 500, 4.34 at 1000, reel of 2,500, out of stock; ichome 4.40 at 2,500. No end-of-life notice found; OmniVision product brief v1.9 is dated April 2026. Sibling OVM7692-RACA is listed obsolete. The ball map is still not public (release gate). The only single-piece US figure in the repository is USD 27.50 at 1 and 6.25 at 2,500 (micro-cameras.md, marked unverified there).
- **Tilt and motion sensor (IMU)**: DigiKey US: 4.42 at 1 (cut tape), 3.06 at 1000, 2.78 at 5,000.
- **Display (memory LCD, 1.28 inch, 128 x 128)**: DigiKey US: 11.42 at 1, 8.82 at 10, 7.305 at 100, 6.7715 at 500. Future 6.23 and Arrow 6.284 at 2,240+. A Sharp change notice was seen on a Future listing: glass supplier AGC to Corning (0.5 mm glass only) from December 2024 production. A review found that this is a family-wide notice which says the glass thickness changes 'for some models' without naming them, and that the second change first reported here (polarizer surface treatment and adhesive type) appears on the listing of a sibling part, the LS011B7DH03, not on this one. Neither change is confirmed for the LS013B7DH03: PROVISIONAL. Get the notice itself, and check the thickness and the front surface of current-production panels against the 0.746 mm in the stack. The Mouser page says obsolete / not sold (looks stale).
- **Display connector (10-way, 0.5 mm pitch, top contact)**: Aggregator: DigiKey 1.31 (cut tape) and 1.25 (Digi-Reel), quantity break not stated; Mouser 1.30 to 1.35; Future 0.95 with 2,000 units. Do not confuse with FH12-10S-0.5SH(55), the bottom-contact version. Which contact side is needed is still a release gate.
- **Flash memory (64 Mbit)**: DigiKey US tray pricing: 2.32 at 100, 2.25 at 250, 2.19 at 570, 2.13 at 1,140; an earlier extract gave 2.68 at 1. bom-verification-ics.md also saw a second, lower price set on a US-page extract (1.53 at 1 falling to 1.22 at 1,140) and called the price not confirmed. Buy this part early with the other long-lead parts.
- **Battery charger chip**: Prices seen: EUR 0.66 at 1 (DigiKey LV); 1.21 at 1 and 0.97 at 100 on the Canada page (currency not confirmed). Non-US: LCSC 0.43 at 1000.
- **Always-on 2.8 V regulator**: Aggregator unit price 0.39 (DigiKey), Octopart 0.37; quantity breaks not seen. Listed Active.
- **3.3 V regulator for the USB supply pin**: Prices seen: CAD 0.79 at 1, 0.61 at 100, 0.60 at 3,000; EUR 0.43 at 10, 0.34 at 100. No USD price seen.
- **Switchable 2.8 V regulator for the cameras**: DigiKey USD: 0.57 at 1, 0.402 at 10, 0.3133 at 100.
- **USB static-discharge protection**: 0.36 at 1, 0.114 at 1000. Carried forward from bom-verification-ics.md (2026-11-11).
- **32.768 kHz crystal (6 pF)**: 0.68 at 1, about 0.45 at 1000 (USD page). Carried forward from bom-verification-ics.md.
- **Photodiode (grain reader)**: EUR 1.96 at 1, about 1.08 at 100, 0.89 to 0.94 at 500 to 1000; USD 0.934 at 5,000 (reel). The pad layout must still be taken from the Vishay drawing.
- **Red LEDs, 0402 (8 per marker)**: Aggregator prices: DigiKey 0.33 at 1 falling to 0.12 at 100; Mouser 0.06 to 0.26. The part number is not in DESIGN_SPEC; it comes from grain-sensing.md and bom-verification-opto.md.
- **Near-infrared LEDs, 0402 (8 per marker)**: USD (DigiKey MX page): 0.62 at 1, about 0.31 at 100, 0.24 at 1000. The part number is not in DESIGN_SPEC. A replacement must be chosen before production. Reported in review, not re-checked: the maker's notice OS-PDN-2026-006 of 4 Feb 2026 gives last order 31 Jan 2027 and last delivery 31 Jan 2028 and names the SFH 4053B as the replacement; the maker's page lists the SFH 4053B as 'full production' with 9 mW/sr typical at 70 mA; one distributor showed it as unavailable. Confirm its footprint and a US distributor. Parts from other makers give less light (Inolux 5.5 mW/sr against 7 mW/sr for the SFH 4053).
- **220 ohm resistor arrays, 4-in-1 (6 per marker)**: Status Active, AEC-Q200. Octopart shows 0.031 (quantity not stated; reel of 10,000).
- **Small N-channel MOSFET**: 0.29 at 1, 0.0734 at 1000. The 1.5 V maximum gate threshold was not confirmed from the datasheet (one listing shows '1.5 V at 1 mA'). DESIGN_SPEC names only 'onsemi BSS138'; the orderable code is chosen here.
- **Schottky diode, 30 V 0.5 A**: 0.30 at 1, 0.07417 at 1000; lifecycle Active. DESIGN_SPEC gives no part number for this diode; this one was proposed in bom-verification-ics.md.
- **Temperature sensor (10 kohm NTC, 0402)**: 0.11 at 1, 0.096 at 5, 0.09 at 10. Change DESIGN_SPEC section 4 to the NCU15 part before the netlist is frozen.
- **Lithium-polymer cell with protection board, 2 x 10 x 30 mm**: 12.00 each with protection board, 10.00 bare (quantity 1), as listed. The listing text may date from September 2024 (reported in review, unconfirmed): treat price and availability as unconfirmed until PowerStream answers. Further price columns (8.20, 4.95, 3.80, 3.38) had no readable quantity labels. UN38.3 is noted on the listing; UL 1642 / IEC 62133 status, protection thresholds and the length with the board were not found.
- **Chip resistors, 0402 (about 30 per marker)**: The count is an estimate: no netlist or bill-of-materials file for the real board exists yet in electrical/.
- **Ceramic chip capacitors, 0402 / 0603 (about 32 per marker)**: The count is an estimate (see the resistor line).

---

## 4. Electronic parts on the charging cradle

The consumer cradle carries four spring pins; the factory fixture carries seven. The design does not yet contain a cradle
schematic, so this list is taken from the YAML, `mechanical/README.md` and the task.

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| USB-C socket | USB4105-GF-A | Where the charging cable plugs into the cradle | [DigiKey (2073-USB4105-GF-ACT-ND)](https://www.digikey.sg/en/products/detail/gct/USB4105-GF-A/11198510) | 0.917 / not seen | 127,697 (aggregator); lead time 9 weeks | low | another 16-pin USB 2.0 Type-C receptacle of the same footprint class (PROVISIONAL) | **VERIFIED** 2026-11-11 |
| Spring pins (4 in the consumer cradle, 7 in the factory fixture) | 0914-0-15-20-77-14-11-0 | Touch the marker's gold pads to charge it and talk to it | [DigiKey (ED8185-ND); Future Electronics](https://azcus.digikey.com/en/products/detail/mill-max-manufacturing-corp/0914-0-15-20-77-14-11-0/1147053) | not seen / 0.88 | DigiKey: 54,990 in stock; lead time 4 weeks. Future: 0 in stock, 3-week factory lead | low | Mill-Max 0914-1 / 0914-2 (longer tails) or the 085x 'power' series with the same stroke | **VERIFIED** 2026-11-11 |
| Resettable fuse on the 5 V line | not specified in the design. PROPOSED rating: holds about 0.2 A, trips at about 0.5 A (the same proposal as COMPLIANCE.md row 15). No order code confirmed | Limits the current if metal bridges the pads (a hard short). It does not react to a film of water | not found (no US distributor listing seen today) | not seen / not seen | not found | low: generic part, many makers | any 1206 or 0805 resettable fuse of that rating, 6 V or more (not searched) | **PROVISIONAL** 2026-11-11 |
| 5.1 kohm resistors (2 per cradle) | class: 5.1k 1 %, 0402 or 0603 | Tell a USB-C charger to switch its 5 V on | DigiKey, Mouser (commodity; not checked) | not seen / not seen | commodity; not checked | low | any equivalent | **PROVISIONAL** (not searched) |

Country of manufacture: not found for any line in this table.

Notes on these lines:

- **USB-C socket**: 1.09 at 1, 0.917 at 10, 0.86 at 25, about 0.57 at 8,000 on reel: seen on DigiKey's Singapore page, which bom-verification-opto.md says showed US dollars. A review reports lower figures on the US page (USD 0.78 at 1, about 0.46 at 1,600 on reel): not re-checked. The currency or date of the first figure is therefore not confirmed. The money is small either way.
- **Spring pins (4 in the consumer cradle, 7 in the factory fixture)**: 0.85 at 1 (DigiKey); 0.88 at 1000+ (Future). Plunger and barrel diameters are still not confirmed from the Mill-Max drawing.
- **Resettable fuse on the 5 V line**: The design gives no rating: mechanical/README.md parts row 22 says only 'resettable fuse on VBUS'. PROPOSED, and the same in COMPLIANCE.md row 15: a part that holds about 0.2 A and trips at about 0.5 A. The cradle draws well under 0.1 A in use (estimate: 20 mA of charge current plus the processor and USB). The 0.5 A-hold part first named here (Littelfuse 1206L050YR) is withdrawn, so that the two documents agree. The fuse covers a hard short only. It cannot protect a wet pad slot: mechanical/README.md open issue 8 estimates the leakage through a water film at 0.1 to 0.6 mA, far below what any such fuse reacts to. Decide the rating and add it to the cradle schematic. Non-US price seen for a part of this kind: LCSC about 0.05.
- **5.1 kohm resistors (2 per cradle)**: Not in DESIGN_SPEC or the YAML; named in the task and in power.md.

---

## 5. Mechanical purchased parts

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Fold prism, 2.0 mm (2 per marker) | 32-526 | Tiny mirror-prisms that turn each camera's view from 'up' to 'forward' | [Edmund Optics (Barrington, New Jersey), direct](https://www.edmundoptics.com/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392/) | 94.50 / quote | '20+ in stock' at the snapshot | medium: easy to buy today, but the largest cost in a small build (about 189 USD per marker at 10 units) | Knight Optical PTK0202 (2 x 2 mm, protected coating, USD 56.02). A UK maker; a review reports a US sales company, Knight Optical (USA) LLC in North Kingstown, Rhode Island (not re-checked). Ask whether PTK0202 ships from US stock and what its size tolerance is | **VERIFIED** 2026-11-11 |
| Fold prism, production volume source | custom: 2.0 mm right-angle, N-BK7, aluminised hypotenuse | Same prism, bought in thousands | [Precision Micro-Optics (catalogue micro prisms); Tower Optical and Edmund Optics by quote](https://pmoptics.com/Right_Angle_Prisms.html) | quote / quote | not found | high until quoted: no published volume price for a 2.0 mm aluminised prism was found | Edmund 32-526 at its 26 to 49 price (78.50) | **PROVISIONAL** 2026-11-11 |
| Ball feet, 1.0 mm (3 per marker) | McMaster-Carr 1598K16 (440C stainless, Grade 25, pack of 250) | The three hard feet the marker stands on | [McMaster-Carr](https://www.mcmaster.com/products/balls/diameter~1-mm/) | not seen / not seen | catalogue item; price and stock not readable in the extract | low | 316 stainless 1 mm balls: Thermo Fisher lists them (25 or 100 pieces, grade not stated) | **VERIFIED** 2026-11-11 |
| Cover glass, EVT (flat mineral-glass watch crystal, 28.0 x 1.0 mm) | Esslinger 'flat round standard mineral glass crystal, 1 mm thick', size 28.0 | Clear window over the display | [Esslinger (St. Paul, Minnesota)](https://www.esslinger.com/watch-crystal-flat-round-standard-mineral-glass-crystal-1mm-thick/) | 1.65 / n/a | sold singly in 0.1 mm size steps from 12 to 40 mm; stock not shown | low for EVT (but this glass is not step-proof) | Jules Borel sapphire crystal 28.0 x 1 mm (11.00 at 1 to 2, 9.90 at 10+). Caution: docs/research/display.md finding 6 advises against sapphire over this display (it is birefringent, which interacts with the LCD polariser and polarised sunglasses); the specification still allows it; to be decided | **VERIFIED** 2026-11-11 |
| Cover glass, production (chemically strengthened, printed black border) | custom: dia 28.0 x 1.0 mm aluminosilicate, ring-on-ring strength 600 MPa or more | Stronger window over the display (the step test is still to be passed) | [Abrisa Technologies (Santa Paula, California), quote](https://www.photonicsonline.com/doc/abrisa-technologies-fabricates-coats-corning-gorilla-glass-0001) | quote / quote | custom; lead time not found | medium: 1.0 mm was not among the stocked Gorilla Glass thicknesses in the Abrisa release seen (0.4, 0.55, 0.8, 1.1, 2.0 mm). A review dates that release to May 2020 and reports that later Abrisa lists differ. What is stocked near 1.0 mm today is not known | sapphire watch crystal 28.0 x 1.0 (Jules Borel, about 10 to 11 USD). Caution: docs/research/display.md finding 6 advises against sapphire over this display (it is birefringent, which interacts with the LCD polariser and polarised sunglasses); the specification still allows it; to be decided | **PROVISIONAL** 2026-11-11 |
| Visor windows, 0.40 mm borosilicate, cut 5.0 x 3.25 mm (2 per marker) | custom, SCHOTT D 263 T eco, 0.4 mm | Small flat windows that keep water out of the two camera openings | [Abrisa Technologies (stocks 0.4 mm sheet and custom-fabricates); Valley Design (custom-cut)](https://www.photonicsonline.com/doc/abrisa-technologies-custom-fabricates-and-optically-coats-schott-d-t-eco-ultra-thin-glass-0001) | quote / quote | sheet stocked at Abrisa per its release; cutting lead time not found | medium: a very small custom part; SCHOTT's own cut-to-size minimum for 0.4 mm glass is 10 x 10 mm, so a dicing house is needed | Edmund Optics stock 0.4 mm D 263 T eco windows, 25 x 25 mm, diced to size (reported in review as stock #18-301, USD 28.50 at 1 to 5: confirm on the page; the 45366 at the end of the web address is a page number, not a stock number) | **PROVISIONAL** 2026-11-11 |
| Pressure-equalisation vent, adhesive, 5.0 mm | VE80205 | A breathable patch: lets air move so the seals are not stressed, and keeps water out | [not found (ask Gore in Newark, Delaware, directly; RS in the UK sells packs of 50)](https://www.gore.com/products/venting/adhesive-vents) | not seen / not seen | US stock not found; an RS Korea page shows a sister size temporarily out of stock | medium: no US distributor found; water-entry pressure and IP rating for this size not found | Porex Virtek adhesive vent disc 5 x 2 mm (Porex is a US-headquartered company, from memory; country of manufacture not found; sold in rolls of 10,000; a review reports IP 64 and IP 67 for its PMV10 membrane on the maker's page: typical values, not re-checked) | **PROVISIONAL** 2026-11-11 |
| Rubber feet for the cradle, about dia 8 x 3 mm (4 per cradle) | not selected (3M Bumpon class) | Stop the cradle sliding | McMaster-Carr or DigiKey (not searched) | not seen / not seen | commodity; not checked | low | any self-adhesive bumper of that size | **PROVISIONAL** (not searched) |
| Screws, M2 x 5 thread-forming for plastic (4 per cradle) | not selected | Hold the cradle's circuit board | McMaster-Carr (not searched) | not seen / not seen | commodity; not checked | low | any M2 thread-forming screw for plastics | **PROVISIONAL** (not searched) |

Country of manufacture: not found for the lines above, except: Pressure-equalisation vent, adhesive, 5.0 mm: Germany (RS listing).

Notes on these lines:

- **Fold prism, 2.0 mm (2 per marker)**: 105.00 at 1 to 5, 94.50 at 6 to 25, 78.50 at 26 to 49 (US page, bom-verification-opto.md). N-BK7, aluminised hypotenuse, dimensional tolerance +/-0.1 mm.
- **Fold prism, production volume source**: Tower Optical: only general prism capability and quote-only pricing were found, no 2.0 mm aluminised catalogue part. Precision Micro-Optics lists micro prisms with an aluminium hypotenuse at about USD 32 to 38 in 1.25 and 1.5 mm sizes; 2.0 mm not confirmed.
- **Ball feet, 1.0 mm (3 per marker)**: Diameter tolerance +/-0.0025 mm, Rockwell C58, magnetic. The part number was read from run-together listing text: confirm it on the page. 440C is hard but rusts more easily than 316; the design says only 'stainless'. No Grade 25 ball in 316 was found at 1 mm.
- **Cover glass, EVT (flat mineral-glass watch crystal, 28.0 x 1.0 mm)**: Listed at 1.50 on one page and 1.65 on another; 5 % off at 10 to 49, 10 % at 50 to 99, 15 % at 100+ (1.65 less 5 % is about 1.57). Diameter and thickness tolerance are not stated: measure on receipt (the recess is 28.5).
- **Cover glass, production (chemically strengthened, printed black border)**: Abrisa states that it strengthens, cuts, CNC-machines, edges, screen-prints and coats Dragontrail, Gorilla Glass and Xensation. The strength figure, the 28.0 mm size and any price are not confirmed. The repository specifies this glass by strength only (ring-on-ring 600 MPa or more) and makes no step-proof claim: mechanical/README.md open issue 3 estimates about 400 MPa in a 1.0 mm crystal under an 800 N step, and 0.2 mm more thickness is the reserved remedy if the step test fails. Ask Abrisa which thicknesses near 1.0 mm it stocks today. A 1.1 mm sheet would leave only 0.02 mm below flush in the 1.25 mm recess; 0.8 mm would need a thicker tape or a shallower recess.
- **Visor windows, 0.40 mm borosilicate, cut 5.0 x 3.25 mm (2 per marker)**: The material and a US fabricator are VERIFIED; the 5.0 x 3.25 mm cut, its tolerance and its price are not. Edmund also lists a 5 mm round 0.4 mm window (stock number not confirmed; 53110 is only its page number), but the recess is rectangular. Anti-reflection coating is best applied to the sheet before cutting.
- **Pressure-equalisation vent, adhesive, 5.0 mm**: RS UK: GBP 2.933 each at 50 and GBP 1.578 at 1000, in packs of 50. 2.0 mm vent area, 5.0 mm outside, 0.26 mm thick, 104 ml/min at 70 mbar (Gore data sheet, via bom-verification-opto.md). The design asks for at least 50 kPa water-entry pressure: unconfirmed.
- **Rubber feet for the cradle, about dia 8 x 3 mm (4 per cradle)**: Generic.
- **Screws, M2 x 5 thread-forming for plastic (4 per cradle)**: Generic.

---

## 6. Tapes and foam

A **converter** is a company that buys tape in wide rolls and cuts it into shaped parts. The tape maker (3M, tesa) does not
sell cut shapes itself. The cutting service is in section 8; this table is the material.

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Adhesive sheet material, circuit board to base plate (FR-4 build) | 3M 93020LE | Double-sided tape that bonds the board to the base plate and seals two openings | [3M US catalogue (54 in x 60 yd rolls); DigiKey; Tekra; supplied cut by a converter](https://3m.com/3M/en_US/p/d/b40072050) | quote / quote | roll product; the converter supplies cut parts | low | 3M 93015LE (0.15 mm; would change the stack height) | **VERIFIED** 2026-11-11 |
| Transfer tape, cover-glass ring (also the sheet of the PA12 build) | 3M 9472LE | Thin film of glue, with no carrier, that holds the cover glass | [CS Hyde (12 x 12 in sheets); TestEquity; DigiKey; Zoro](https://catalog.cshyde.com/printitem/3m-products/3m-adhesive-transfer-tapes/3m9472le) | quote / quote | sheets and rolls listed at several US sellers | low | 3M 468MP (0.13 mm, a different adhesive family) | **VERIFIED** 2026-11-11 |
| Adhesive frame for the display, 0.15 mm foam type | not selected. Candidate: 3M VHB 5906 (0.15 mm, black) | Sticks the display under the roof ledge | [DigiKey (thin VHB 5906-5915 page); converters](https://tbpconverting.com/wp-content/uploads/2022/02/PDS-3M-5906-5907-5908-5909-TBP-Converting.pdf) | quote / quote | not found | low | 3M 468MP (0.13 mm, not a foam) | **PROVISIONAL** 2026-11-11 |
| Opaque black double-coated tape for the baffle annulus, 0.13 mm | not selected. Candidates: tesa 61361 or tesa 88672 (0.10 mm); 3M 9495B (0.145 mm) | Blocks stray light under the baffle ring | [through converters; 3M 9495B seen at TestEquity](https://www.tesa.com/en/industry/tesa-61361.html) | quote / quote | not found | medium: no black light-blocking double-coated tape of exactly 0.13 mm was found | black liquid adhesive (the fallback named in mechanical/README) | **PROVISIONAL** 2026-11-11 |
| Cell fixing adhesive, 0.05 mm or thinner | not selected. No tape of 0.05 mm or less was identified | Tacks the battery to the board | DigiKey or a converter (not searched) | not seen / not seen | not found | low for supply. Design item: the tapes named so far are thicker than the 0.05 mm limit | 3M 467MP and 3M 9471LE are both about 0.058 mm (2.3 mil), so neither meets the 0.05 mm in this line's title (thickness reported in review from 3M and distributor pages, in line with the 'about 0.06 mm' in enclosure-manufacturing.md; not re-checked) | **PROVISIONAL** (not searched) |
| Foam pad under the display, 0.3 mm | Rogers PORON 4790-92 class, 0.3 mm, adhesive one side, 26.6 x 10 mm | Soft cushion that lets the battery swell without pushing on the display | [Stockwell Elastomerics (Rogers Preferred Converter); CGR Products](https://www.stockwell.com/poron-foam-cellular-urethane/) | quote / quote | Stockwell says it stocks the 4701 and 4790 families; the 0.3 mm gauge is not confirmed | low | another PORON grade offered at 0.3 mm (choose with the converter) | **PROVISIONAL** 2026-11-11 |

Country of manufacture: not found for any line in this table.

Notes on these lines:

- **Adhesive sheet material, circuit board to base plate (FR-4 build)**: 0.20 mm (7.9 mil), polyester film carrier, 300LSE adhesive: this confirms the YAML thickness that was marked provisional. Die-cut pattern GL1-030.
- **Transfer tape, cover-glass ring (also the sheet of the PA12 build)**: 5.2 mil (0.13 mm) 300LSE transfer tape. CS Hyde lists a 12 x 12 in sheet at USD 6.33; TestEquity a 1/2 in x 60 yd roll at USD 17.92. Die-cut patterns GL1-033 (ring) and GL1-031 (PA12 build).
- **Adhesive frame for the display, 0.15 mm foam type**: The 0.15 mm thickness of VHB 5906 was confirmed in bom-verification-opto.md; the choice itself is open. Pattern GL1-032 with its vent channel.
- **Opaque black double-coated tape for the baffle annulus, 0.13 mm**: tesa 61361 and 88672: 100 um black PET with black acrylic adhesive, described as light blocking. 3M 9495B: 0.145 mm, black PET carrier, 200MP adhesive (light blocking not stated). tesa 61395 is 0.20 mm. The ring is lapped to height, so 0.10 or 0.145 mm can be absorbed if the YAML is updated. Pattern GL1-034.
- **Cell fixing adhesive, 0.05 mm or thinner**: Class only. The YAML (battery.fixing_adhesive_max) allows 0.05 mm. The 467MP / 9471LE family is about 0.058 mm and does not meet it. Either relax the limit to 0.06 mm (that takes 0.01 mm from the 0.15 mm left above a swollen cell, mechanical/README.md open issue 13) or find a thinner transfer tape; none was searched for today.
- **Foam pad under the display, 0.3 mm**: Sources disagree on whether 4790-92 exists at 0.3 mm: an availability booklet lists item 4790-92-30012-04 at 0.012 in, while Rogers' page gives 0.53 mm as the thinnest.

---

## 7. Adhesives, by class

The design names what each glue must do, not which product to use. The first table restates each class. The second table
names **candidates**: real products sold in the US whose data sheets, as far as they were seen, come close. **A candidate
is a starting point for a coupon test, not a selection.** No candidate has been tested on this product's materials
(vapor-smoothed nylon PA12, solder mask, routed FR-4, glass).

| Adhesive class | What it does | What the design asks for | Candidates named below | Supply and technical risk | Status |
|---|---|---|---|---|---|
| Perimeter seal adhesive (class) | The black glue bead that seals the base to the shell (about 70 mm3 per marker) | Requirement (mechanical/README): opaque black, thixotropic, work life 1 h or more, cures at room temperature or 45 C at most, sustained peel at 70 C on primed PA12 and on FR-4 solder mask. | candidates: 3M Scotch-Weld DP490; Huntsman Araldite 2031-1 (3M DP420NS Black fails the work-life need) | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-11 |
| Ball-foot potting epoxy (class) | Locks each ball foot in its hole (stage 1 dual-cure or two-part; stage 2 two-part, room temperature) | Stage 2 cures between two opaque boards, so light cannot reach it. About 1 mm3 per foot. | candidates: Loctite EA E-30CL; EPO-TEK 301; 3M Scotch-Weld DP460; stage 1 option Dymax Multi-Cure 6-621-GEL | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-11 |
| Visor-window adhesive, thixotropic light-cure (class) | A gel that is cured with light; it frames each window without creeping behind the glass | Must not wick: adhesive at the roof edge of the opening would clip the cameras' upper field. About 1 mm3 per window. | candidates: Dymax Multi-Cure 6-621-GEL; Dymax 3022-GEL; Dymax 3094-GEL | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-11 |
| Clear optical potting for the grain opening (class) | Clear, hard fill that keeps mud and dew off the grain LEDs and photodiode (about 0.1 ml per marker) | Requirement: clear, low fluorescence, non-yellowing, mixed viscosity about 0.1 to 2 Pa.s, cure at 60 C at most, low shrinkage, chosen modulus. | candidates: EPO-TEK 301; EPO-TEK 301-2; Master Bond EP30-2 | low for supply; high technical risk: 'low fluorescence' is not documented for any candidate, and one candidate's recommended cure (80 C) is above the 60 C process limit | **PROVISIONAL** 2026-11-11 |
| Hood gasket bead, black, soft, silicone-free (class) | Soft bead that closes the slit above each camera against stray light | Requirement: black, about Shore A 40, silicone-free, form-in-place, holds a 0.5 x 0.33 mm bead. No candidate is confirmed opaque black. | candidates: Dymax GA-140 (Shore A35); Dymax GA-112 (Shore A50, 'black translucent'); Dymax GA-142 (softer) | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-11 |
| Cover-glass rim sealant, black, wicking grade (class) | Thin black sealant that runs into the 0.25 mm gap round the cover glass | Open item. | none found | medium: no product was identified today that is black, wicks into a 0.25 mm gap and is sold in the US | **PROVISIONAL** 2026-11-11 |
| Prism bonding adhesive, UV-cure (class) | Tacks each prism to its camera at four corners | Class only; not searched today. | any low-shrink optical UV adhesive | low | **PROVISIONAL** (not searched) |
| Primer or plasma treatment for the nylon bonding faces (class) | Prepares the printed nylon so that tapes and glues grip it | Follow the chosen adhesive maker's advice. | plasma or corona treatment by the printing bureau or in-house | low | **PROVISIONAL** (not searched) |
| Thermal adhesive for the temperature sensor (class) | A dab that couples the temperature sensor to the cell | Class only; not searched today. | any electrically insulating thermal adhesive that cures at 45 C or less | low | **PROVISIONAL** (not searched) |

### Candidates (not selections)

| Class and candidate | Product | Maker | US source | Data-sheet properties and remarks | Status |
|---|---|---|---|---|---|
| Perimeter seal, candidate A | 3M Scotch-Weld DP490 (black) | 3M | [3M US catalogue (400 mL cartridge, 6 per case); 50 mL cartridges seen only at Farnell (Europe)](https://www.3m.com/3M/en_US/p/d/v101722005/) | Data-sheet properties seen: black, thixotropic gap-filling two-part epoxy, mix 2:1, work life 90 min, room-temperature cure (test data after 7 days at 23 C), temperature resistance to 120 C, bell peel 34.5 N/cm (Canadian data sheet). On paper it meets colour, thixotropy, work life and cure limit. Not tested on PA12 or solder mask. Confirm a 50 mL pack in the US. | **VERIFIED** 2026-11-11 |
| Perimeter seal, candidate B | Araldite 2031-1 | Huntsman | [Chemical Concepts; Perigee Direct (50 mL)](https://www.chemical-concepts.com/product/aralditer-2031-epoxy-adhesive/) | Black, toughened, thixotropic (non-sag to 10 mm), mix 1:1, room-temperature cure, pot life 60 to 70 min for 100 g (Huntsman comparison sheet), described as having good adhesion on polyamides. The peel table was not readable in the extract. | **VERIFIED** 2026-11-11 |
| Perimeter seal, candidate C (benchmark; fails the work-life need) | 3M Scotch-Weld DP420NS Black | 3M | [3M US catalogue; gluegun.com](https://eaa.3m.com/3M/en_US/p/d/b40066483/) | Black, toughened, non-sag, 2:1, work life 20 min (the design asks for 1 h or more), handling strength in about 2 h, full cure in 24 h at 22 C. | **VERIFIED** 2026-11-11 |
| Ball potting, candidate A | Loctite EA E-30CL | Henkel | [Ellsworth Adhesives (200 mL cartridge); Perigee Direct](https://ellsworth.com/products/adhesives/epoxy/henkel-loctite-hysol-e-30cl-epoxy-adhesive-clear-200-ml-cartridge) | Clear, low viscosity, two-part 2:1, 30 min work life, full cure in 24 h at room temperature, lap shear 21 N/mm2 on grit-blasted steel (Henkel data sheet, January 2018). | **VERIFIED** 2026-11-11 |
| Ball potting, candidate B; clear potting, candidate A | EPO-TEK 301 | Epoxy Technology (Meridian Adhesives) | [Fiber Optic Center (4 g and 8 oz kits)](https://media.focenter.com/CMP1007/files/EPOTEK301SpectrallyTransparentEpoxyRoomTemperatureCure8oz_ET301-8OZ_fiberopticcenter_REV2.pdf) | Two-part, very low viscosity, mix 20:5 by weight, pot life 1 to 2 h, cure 65 C for 1 to 2 h or 23 C for 24 h, transmission 99 % or more from 382 to 980 nm, refractive index 1.519. Viscosity value, hardness, shrinkage and fluorescence were not seen. | **VERIFIED** 2026-11-11 |
| Ball potting, candidate C | 3M Scotch-Weld DP460 | 3M | not searched | Off-white toughened epoxy, 2:1, about 60 min work life: from memory, not checked today. | **PROVISIONAL** (not searched) |
| Window adhesive, candidate A (also a stage-1 option for the ball feet) | Dymax Multi-Cure 6-621-GEL | Dymax | [TestEquity; Jensen Tools](https://www.testequity.com/product/10000994-6-621-30ML) | Light-cure gel that also cures with heat or an activator in shadowed areas; Dymax names metal, glass, ceramic, phenolic and filled polyamide. Price seen per 30 mL syringe, not per unit: USD 112.77 for one syringe, 99.24 each at 100 syringes. Adhesion to unfilled, vapor-smoothed PA12 is not shown. | **VERIFIED** 2026-11-11 |
| Window adhesive, candidate B | Dymax 3022-GEL | Dymax | not found (no US distributor listing seen); Dymax direct | Preliminary data sheet: the gel version is 50,000 cP against 500 cP for the base grade; 'strong bonds to glass and plastic'. | **PROVISIONAL** 2026-11-11 |
| Window adhesive, candidate C | Dymax 3094-GEL | Dymax | [Ellsworth Adhesives (30 mL MR syringe)](https://www.ellsworth.com/products/by-manufacturer/dymax/adhesives/uv-curing/dymax-ultra-light-weld-3094-gel-uv-curing-adhesive-yellow-30-ml-mr-syringe/) | Thixotropic, low-stress plastic bonder (LCP, PC, PU and PS are named); glass is not named; yellow. The listed price of USD 1,186.75 looks like a case price or an error: confirm. | **VERIFIED** 2026-11-11 |
| Clear potting, candidate B | EPO-TEK 301-2 | Epoxy Technology (Meridian Adhesives) | [Fiber Optic Center; Meridian Adhesives](https://products.meridianadhesives.com/storage/downloads/xjagq6xi1luav3sdwj9yuwpee21igy91/301-2-rev-xviii-2.pdf) | Optical grade, low viscosity, long pot life. Recommended cure 80 C for 3 h; 'minimum alternative' 23 C for 48 h, which may not reach the data-sheet properties. The 80 C cure is above the 60 C limit of assembly step 12. Fluorescence data not found. | **VERIFIED** 2026-11-11 |
| Clear potting, candidate C | Master Bond EP30-2 | Master Bond | [Master Bond, direct (US-headquartered company, from memory; country of manufacture not found)](https://datasheets.globalspec.com/ds/Master-Bond/ep30-2/bc0f0830-873b-4300-aa6f-c24a19ca3650) | Described as an optically clear, lower-viscosity, room-temperature-curing two-part epoxy that meets NASA low-outgassing limits. Viscosity, shrinkage, yellowing and fluorescence figures were not seen. | **VERIFIED** 2026-11-11 |
| Hood gasket, candidate A | Dymax GA-140 | Dymax | [Dymax, direct or through its distributors (US-headquartered company, from memory; country of manufacture not found)](https://dymax.com/products/formulations/light-curable-materials/gasketing) | UV-cure form-in-place gasket, Shore A35, silicone-free, soft and tack-free. Colour not found: the design needs an opaque black bead. | **VERIFIED** 2026-11-11 |
| Hood gasket, candidate B | Dymax GA-112 | Dymax | [Dymax, direct or through its distributors (US-headquartered company, from memory; country of manufacture not found)](https://aleo.dymax.com/products/formulations/light-curable-materials/gasketing/ga-112) | Shore A50, silicone-free, listed as 'black translucent' in a Dymax brochure. Harder than the Shore A 40 target, and translucent: a light-leak test is needed. | **VERIFIED** 2026-11-11 |
| Hood gasket, candidate C | Dymax GA-142 | Dymax | [Dymax, direct or through its distributors (US-headquartered company, from memory; country of manufacture not found)](https://dymax.com/products/formulations/light-curable-materials/gasketing/ga-142) | Shore 00-55 (much softer than Shore A 40), silicone-free. Colour not found. | **VERIFIED** 2026-11-11 |

What the candidate search showed:

- **Perimeter seal.** Only two products seen meet "black, thixotropic, an hour or more of work life, room-temperature cure" on
  paper: 3M DP490 and Araldite 2031-1. The popular 3M DP420NS Black is listed only to show why it does not fit (20 minutes).
- **Clear potting.** The better-known optical epoxy (EPO-TEK 301-2) wants 80 C for its recommended cure, above the 60 C limit of
  assembly step 12. Its room-temperature alternative is described by the maker as possibly not reaching data-sheet properties.
  EPO-TEK 301 cures at room temperature in 24 hours. **No fluorescence figure was found for any of them**; it has to be measured.
- **Hood gasket.** The soft silicone-free light-cure gaskets seen are clear or "black translucent", not opaque black.
- **Cover-glass rim seal.** Nothing found. Open item.

---

## 8. Custom parts and outside services

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Main circuit board, bare (4 layers, 0.8 mm, ENIG, 0.10 / 0.10 mm in the fine areas, through vias) | custom (Gerber set; outline GL1-040) | The board that carries every electronic part | [Bay Area Circuits (Fremont, California); Sierra Circuits (Sunnyvale, California); AdvancedPCB (custom service)](https://bayareacircuits.com/pcb-capabilities/) | quote / quote | Sierra advertises turn times from 1 day; others not seen | low to medium: the capability is published, but 0.100 mm is 1.6 um under '4 mil' (0.1016 mm), plugged-and-covered vias were not found in any published tier, and the standard-tier figure may hold for outer layers only (reported in review, not re-checked) | Summit Interconnect / Royal Circuits (advanced tier) | **VERIFIED** 2026-11-11 |
| Circuit-board assembly (both sides, two camera cubes, LGA sensor, 64-pin processor, 0402 parts) | service | Machine-placing and soldering the parts onto the board, with X-ray of the hidden joints | [MacroFab (Houston, Texas); AdvancedPCB assembly; Sierra Circuits (turnkey)](https://www.macrofab.com/pcba/) | quote / quote | Sierra advertises turnkey boards in as fast as 5 days; others not seen | medium: the camera cubes are reflowed with their lenses on, need X-ray, and their land pattern is still unverified | Screaming Circuits; CircuitHub (capabilities not found today) | **VERIFIED** 2026-11-11 |
| Base plate, routed 0.80 mm FR-4, no copper, matte black mask (drawing GL1-011) | custom (drawing GL1-011 and its fab files) | The flat underside of the marker; carries the ball feet | [Bay Area Circuits; Sierra Circuits; AdvancedPCB (to be asked with the drawing)](https://bayareacircuits.com/pcb-capabilities/) | quote / quote | not found | low | printed PA12 plate GL1-012 (the documented alternative build) | **PROVISIONAL** 2026-11-11 |
| Base plate, alternative build: printed PA12, 0.87 mm, with integral baffle (drawing GL1-012) | custom (drawing GL1-012) | The same underside plate, printed in nylon: for the 4 EVT units and the shells of the all-printed comparison | [Protolabs; Xometry; Fictiv; Hubs (Protolabs Network): the bureaus of the tub line, to be asked with the drawing](https://www.protolabs.com/services/3d-printing/multi-jet-fusion/) | quote / quote | not found | medium: bureaus quote +/-0.2 to 0.3 mm, which is wide for a 0.87 mm plate whose thickness and flatness set the height of the ball feet; earlier research expects thin printed discs to warp 0.2 to 0.5 mm (unverified) | the FR-4 plate GL1-011 (the primary build) | **PROVISIONAL** 2026-11-11 |
| Cradle circuit board (2 layers, 1.6 mm, 30 x 22 mm) and its assembly | custom | Small board that carries the USB-C socket and the spring pins | [OSH Park (2-layer prototype service) or any US board shop](https://oshpark.com/pricing) | quote / quote | not found | low | any US 2-layer board service | **PROVISIONAL** 2026-11-11 |
| 3D printing of the tub (HP Multi Jet Fusion PA12, dyed black, vapor smoothed) | custom (drawing GL1-010) | The black nylon top shell of the marker | [Protolabs; Xometry; Fictiv; Hubs (Protolabs Network)](https://www.protolabs.com/services/3d-printing/multi-jet-fusion/) | quote / quote | bureau lead time not confirmed for this part | medium: 0.8 mm walls are at the bottom of the published vapor-smoothing minimums (0.76 mm to about 1 mm; 1.5 mm on one page reported in review), and bureau tolerance (+/-0.2 to 0.3 mm) is wide against the +/-0.1 mm the seal face needs | Jawstec (lists MJF PA12, 1 mm minimum wall); Forecast 3D, Endeavor 3D, DI Labs, RapidMade (no results today) | **VERIFIED** 2026-11-11 |
| 3D printing of the baffle-ring sets (MJF PA12, dyed black, not smoothed) | custom (drawing GL1-013) | Small black ring that shades the photodiode | [Protolabs; Xometry; Fictiv; Hubs (Protolabs Network)](https://www.protolabs.com/services/3d-printing/multi-jet-fusion/) | quote / quote | not found | low | integral baffle of the PA12 base plate (alternative build) | **VERIFIED** 2026-11-11 |
| 3D printing of the cradle body (MJF PA12, not smoothed, not tumbled) | custom (drawing GL1-020) | The charging cradle's body with its lip and latch | [Protolabs; Xometry; Fictiv; Hubs (Protolabs Network)](https://www.protolabs.com/services/3d-printing/multi-jet-fusion/) | quote / quote | not found | low | injection moulding at volume (not studied) | **VERIFIED** 2026-11-11 |
| Die cutting of the adhesive parts (patterns GL1-030, -031, -032, -033, -034) | service | Cutting the tapes to shape, like a pastry cutter for sticky sheet | [3M Preferred Converters: Marian; Strouse; Sur-Seal. Also JBC Technologies and CS Hyde](https://3m.com/3M/en_US/converter-solutions-us/applications/prototyping) | quote / quote | not found | low to medium: the 0.8 mm wide annulus and the 1.5 mm ring are delicate; the small-lot price is unknown | in-house cutting on a desktop plotter for EVT (not verified) | **VERIFIED** 2026-11-11 |
| Glass cutting and finishing service | service | Cuts the visor windows and makes the production cover glass | [Abrisa Technologies; Valley Design](https://valleydesign.com/wp-content/uploads/2023/11/schott-d263.pdf) | quote / quote | not found | medium (see the two glass lines) | Swift Glass, Coresix, S.I. Howard Glass, Cat-i Glass (named in earlier research; not found today) | **VERIFIED** 2026-11-11 |
| Fixtures: laser-cut and sheet parts (nests, masks, press plates) | service | Flat parts for the assembly jigs | [SendCutSend](https://sendcutsend.com/faq/what-is-your-cut-tolerance/) | quote / quote | prices shown per part from quantity 1 | low | Ponoko, OSH Cut, Xometry sheet cutting (not checked) | **VERIFIED** 2026-11-11 |
| Fixtures: precision machined gauges (ball gauge plate with reamed 0.60 mm holes, lapping gauge, go gauges, dummy unit, calibration nest) | custom | Hard reference tools that set the ball-foot height and check the printed parts | a CNC machine shop (Xometry, Protolabs or local): not checked today | quote / quote | not found | low | in-house machining | **PROVISIONAL** (not searched) |
| FCC Part 15 Subpart B emissions test (unintentional radiator, Class B) | service | The radio-noise test a digital product needs before it is sold in the US | [Compliance Testing (compliancetesting.com; offers Part 15B testing); other US EMC labs](https://compliancetesting.com/fcc-testing-and-verification/) | quote / quote | typical bookings of 1 to 3 weeks (estimate carried from rules-compliance.md, unverified) | low | Element, DLS Electronic Systems, Nemko (named in rules-compliance.md; not checked) | **VERIFIED** 2026-11-11 |
| Selective hard gold on the contact pads (production boards only) | process option | Wear-resistant gold on the seven pads the spring pins touch | board fabricator (quote) | quote / quote | not found | low | ENIG, as on the EVT boards | **PROVISIONAL** (not searched) |

Country of manufacture: not found for any line in this table.

Notes on these lines:

- **Main circuit board, bare (4 layers, 0.8 mm, ENIG, 0.10 / 0.10 mm in the fine areas, through vias)**: Published capability (bom-verification-opto.md, 2026-11-11): Bay Area Circuits 0.004 in track and space standard, 0.002 in advanced, ENIG in both tiers, 0.006 in finished hole standard on boards 0.031 in or thinner; Sierra standard product 4 mil; AdvancedPCB standard 5/5 mil, so this board needs its custom service, where ENIG and mask-plugged vias are also listed. OSH Park cannot build it (no 0.8 mm 4-layer). Reported in review, not re-checked: Bay Area Circuits' capability sheet of December 2025 gives the 0.004 in standard figure for outer layers at 1 oz finished copper, and 0.005 in for 1 oz inner layers. If any fine-class track runs on an inner layer the board may leave the standard tier (section 12, item 3). No price is published.
- **Circuit-board assembly (both sides, two camera cubes, LGA sensor, 64-pin processor, 0402 parts)**: MacroFab publishes BGA / LGA down to 0.4 mm ball pitch, X-ray inspection and double-sided assembly; AdvancedPCB assembly publishes no minimum order, BGA / micro-BGA / CSP placement and 3D X-ray (bom-verification-opto.md). OmniVision describes the OVM7692 as reflowable. The cell and prisms are fitted later by hand (assembly step 13). Earlier research (unverified) notes that MacroFab also uses partner factories outside the US: ask for a US build site in writing.
- **Base plate, routed 0.80 mm FR-4, no copper, matte black mask (drawing GL1-011)**: No fabricator page seen says that it will build a copper-free, mask-only plate, hold 0.80 +/-0.10 mm over the mask or supply matte black mask: ask with the drawing.
- **Base plate, alternative build: printed PA12, 0.87 mm, with integral baffle (drawing GL1-012)**: HP Multi Jet Fusion PA12, dyed black, NOT vapor smoothed, 43.5 x 40.0 x 0.87 mm, 1.1 cm3 (mechanical/README.md section 2). The process is the one seen on the tub line. No bureau page seen says that it will hold thickness or flatness on a plate this thin, so the line stays PROVISIONAL. It is not in the per-unit figures (those price the FR-4 build); it is costed in section 10.5 at $8 each, assumed.
- **Cradle circuit board (2 layers, 1.6 mm, 30 x 22 mm) and its assembly**: OSH Park's 2-layer price is from memory (about USD 5 per square inch for three boards); today's search showed only its 4-layer price (USD 10 per square inch for three).
- **3D printing of the tub (HP Multi Jet Fusion PA12, dyed black, vapor smoothed)**: Published figures: Protolabs MJF minimum wall 0.020 in (0.508 mm), minimum feature 0.02 in, parts dyed black, vapor smoothing offered for PA12 black (roughness from 250+ down to 64-100 uin Ra) with a 0.030 in (0.762 mm) minimum wall; Xometry +/-0.3 % with a floor of +/-0.2 or 0.3 mm and about 1 mm minimum wall for smoothing; Fictiv +/-(0.3 mm + 0.002 mm/mm) and 'walls under 1.5 mm do not smooth as uniformly'; Hubs 0.7 mm supported walls. Reported in review, not re-checked: a second Protolabs page (its UK Multi Jet Fusion page) asks for a 1.5 mm minimum wall 'for proper smoothing'. Protolabs' own MJF tolerance was not seen. Xometry, Fictiv and Hubs pass orders to partner shops: ask for US production in writing.
- **3D printing of the baffle-ring sets (MJF PA12, dyed black, not smoothed)**: Printed as sprued sets of six; lapped to height in-house.
- **3D printing of the cradle body (MJF PA12, not smoothed, not tumbled)**: 27 cm3; the build direction is locked and must be confirmed on the order.
- **Die cutting of the adhesive parts (patterns GL1-030, -031, -032, -033, -034)**: 3M states that converters use laser, water jet and plotters for small prototype runs; Strouse advertises tool-free digital converting; Marian lists laser cutting and rapid prototyping. No minimum order or price was seen. GL1-031 is the sheet of the PA12 build (0.13 mm transfer tape cut with the baffle pattern); 4 of the 10 EVT units and half of the extra shells need it.
- **Glass cutting and finishing service**: The cost is carried on the visor-window and production cover-glass lines.
- **Fixtures: laser-cut and sheet parts (nests, masks, press plates)**: Laser tolerance +/-0.005 in on metal parts under 12 in and about +/-0.009 in on plastics. Its page says all cutting is done at its own sites in Nevada, Kentucky and Texas; where the sheet material is made is not stated. Fixture cost is kept out of the per-unit figures (see the roll-up).
- **Fixtures: precision machined gauges (ball gauge plate with reamed 0.60 mm holes, lapping gauge, go gauges, dummy unit, calibration nest)**: Needs grinding and reaming beyond laser-cut accuracy. Also to buy: granite surface plate, positive-displacement dispenser, vacuum bell, UV lamp, pogo test block, leak-test chamber. Budget in the roll-up.
- **FCC Part 15 Subpart B emissions test (unintentional radiator, Class B)**: The GL-1 has no radio, so it follows the Supplier's Declaration of Conformity route: test, keep the report, name a US responsible party. Cost figures seen: USD 800 to 2,000 for testing alone, 1,500 to 5,000 with documentation (from a low-reliability guide site and lab marketing pages: get quotes). Test the marker in its cradle with a USB cable and charger attached. One-time cost, not in the per-unit figures.
- **Selective hard gold on the contact pads (production boards only)**: Not published as a standard-tier option by any fabricator checked. Its cost is assumed inside the q1000 bare-board figure.

Which circuit-board fabricators need an "advanced" service for this board (carried from `research/bom-verification-opto.md`,
checked 2026-11-11):

| Fabricator (US) | Published track and gap | Tier this board lands in | Remark |
|---|---|---|---|
| Bay Area Circuits | 0.004 in standard; 0.002 in advanced. Reported in review, not re-checked: these are outer-layer figures at 1 oz finished copper; 1 oz inner layers are 0.005 in | **standard**, if 0.100 mm is accepted as 4 mil and the fine class stays on the outer layers | ENIG in both tiers; finished hole 0.006 in standard on boards 0.031 in or thinner |
| Sierra Circuits | standard product 4 mil; about 3 mil minimum | **standard product**, same condition | turn times from 1 day advertised |
| AdvancedPCB | standard 5 / 5 mil; custom to 2.75 / 3 mil | **custom (quoted) service** | ENIG and mask-plugged vias are also custom-service items |
| Summit Interconnect (Royal Circuits) | 0.003 in is "advanced" | **advanced** | quick-turn tier figures not found |
| OSH Park | 5 / 5 mil | cannot build it | no 0.8 mm 4-layer service |

Published figures of the printing bureaus (HP Multi Jet Fusion, PA12):

| Bureau | Minimum wall | Tolerance | Dye and vapor smoothing | Seen |
|---|---|---|---|---|
| Protolabs | 0.020 in (0.508 mm) for MJF; 0.030 in (0.762 mm) if vapor smoothed (US vapor-smoothing page). Reported in review, not re-checked: its UK MJF page asks for 1.5 mm "for proper smoothing" | not seen | dyed black as standard; vapor smoothing offered, roughness 250+ down to 64-100 microinch Ra | today and in bom-verification-opto.md |
| Xometry | pages differ: 0.5 to 0.8 mm; about 1 mm if vapor smoothed | +/-0.3 % with a floor of +/-0.2 or +/-0.3 mm (pages differ) | offered | bom-verification-opto.md |
| Fictiv | not seen | +/-(0.3 mm + 0.002 mm per mm), general figure | walls under 1.5 mm do not smooth as uniformly; grey parts turn near-black when smoothed | today |
| Hubs (Protolabs Network) | 0.7 mm supported | not seen | dyed black offered; thin walls may be unsuitable for smoothing | today |
| Jawstec | 1 mm | not readable | not confirmed | today |
| Forecast 3D, Endeavor 3D, DI Labs, RapidMade | no result | no result | no result | not found |

Published vapor-smoothing minimums therefore range from 0.76 mm to about 1 mm, and to 1.5 mm on one page reported in
review, even within one bureau. The tub's 0.8 mm roof and walls are at the bottom of that range. Ask each bureau in
writing, as `mechanical/README.md` section 4.2 already says.

---

## 9. The three highest supply risks in depth

### 9.1 Camera cube: OmniVision OVM7692-RYAA

A camera cube is a complete tiny camera, sensor and lens in one block of 2.95 x 3.47 x 2.76 mm, that is soldered to the
board like a chip.

| Question | What was found | Source and status |
|---|---|---|
| How old is it? | OmniVision's launch press release for the "VGA CameraCube for mobile and notebook markets" was found, without a date in the extract. About 2010, from memory. | ovt.com press release; year PROVISIONAL |
| Is it still made? | No end-of-life, "not recommended" or last-time-buy notice was found. The product page is live and product brief v1.9 sits under an April 2026 path on the maker's site. One listing shows -RYAA as "Active". | ovt.com; pcxco.com listing; VERIFIED as "no notice found", not as a promise |
| Warning signs? | Sibling -RACA is listed obsolete. RS says it will stop stocking sibling -RAAA. An undated DigiKey forum note says the older OVM7690 is no longer on OmniVision's site and that the OVM7692 is "the current VGA cube". | microchipusa.com, seekcomp.com, RS, forum.digikey.com; VERIFIED as seen |
| Who stocks it in the US? | DigiKey only (884-1027-1-ND): 6,282 pieces, lead time 20 weeks, in an undated aggregator copy. No Mouser, Arrow or Avnet listing appeared. Brokers list it; brokers are not a safe source for an optical part. | findchips.com; VERIFIED as a snapshot |
| Minimum order? | 1 piece on cut tape at DigiKey. A full reel is 2,500 (LCSC listing). | findchips.com, lcsc.com |
| Price? | DigiKey: only a range, USD 6.25 to 44.95. Elsewhere: USD 11.45 at 1, 4.42 at 500, 4.34 at 1000 (LCSC, China, out of stock); 4.40 at 2,500 (ichome). The repository's only single-piece US figure is USD 27.50 at 1 and 6.25 at 2,500 (`research/micro-cameras.md`, unverified there); the roll-up uses 27.50 for the 10-unit build. | aggregator extracts; DigiKey price breaks **not found** |
| Drop-in alternative? | **None.** -RAAA is 2.815 x 3.179 x 2.60 mm, so prism height, hoods and pads all change. The other OmniVision cubes seen at DigiKey (OVM6948, OVM6946, OCHTA10) are tiny medical cameras with analog or SPI outputs (400 x 400 pixels where stated), not the 8-bit parallel output this design uses. | bom-verification-ics.md; digikey listings; VERIFIED |
| Can an assembler solder it? | OmniVision describes it as a reflowable camera. The reflow limits and lens protection must be read from the registered datasheet. | ovt.com press release; details PROVISIONAL |

### 9.2 Display: Sharp LS013B7DH03

| Question | What was found | Source and status |
|---|---|---|
| Is it still made? | Listed Active at DigiKey and Future; "Production" on Ciiva and Octopart. Mouser's page says obsolete and not sold, which looks stale. | VERIFIED as seen, with that conflict |
| US stock? | DigiKey US page: 0, with a 28-week manufacturer lead time. Other DigiKey regional pages show 613 to 11,356 in undated snapshots. Future, Arrow, Avnet: 0. | VERIFIED as snapshots |
| Price? | USD 11.42 at 1, 8.82 at 10, 7.305 at 100, 6.7715 at 500 (DigiKey US). 6.23 (Future) and 6.284 (Arrow) at 2,240 or more. | VERIFIED as seen |
| Any change to the part? | **Not confirmed for this part.** A Sharp change notice was seen on a Future listing: glass supplier AGC (0.7 / 0.6 / 0.5 mm) to Corning (0.5 mm only), planned from December 2024 production; reason "end of life of materials". Reported in review: it is a family-wide notice (the same text sits on the listings of other Sharp memory displays) and says the thickness changes "for some models" without naming them. The second change first reported here, a new polarizer surface treatment and adhesive type, was found by that review on the listing of a sibling part (LS011B7DH03), not on this one. | futureelectronics.com extracts; the original Sharp notice was **not seen**; which part the page first cited (p/6117773) belongs to was not confirmed. **PROVISIONAL** |
| Is Sharp leaving the business? | Reports say Sharp will stop its Kameyama No. 2 LCD plant in December 2026 and end in-house production of conventional industrial LCDs. A distributor's press release (April 2026) says Sharp will keep serving industry with its memory-in-pixel technology, which is the technology of this display. Nothing seen names the LS013B7DH03. | data-modul.com, trade press; VERIFIED as reported, meaning for this part unknown |
| Second source? | None that drops in. The JDI LPM013M126A is also a 1.28 inch memory display, but 176 x 176 colour, with a different glass outline; it was found only at a Japanese hobby shop, and its sister part is discontinued. The specification already notes that Sharp's smaller LS010B7DH04 has no US listing. | data-modul.com datasheet, switch-science.com; VERIFIED as seen |

### 9.3 Battery: 2 x 10 x 30 mm lithium-polymer cell with protection board

| Question | What was found | Source and status |
|---|---|---|
| Who sells it in the US? | PowerStream Technology, Orem, Utah: GM201030-PCB, 43 mAh, 2 x 10 x 30 mm, USD 12.00 each with the protection board (10.00 bare), quantity 1. Reported in review: the page may carry a date of 27 September 2024 (one extract; a second search did not confirm it). So the price and the availability are unconfirmed until PowerStream answers. | powerstream.com listing; VERIFIED as a listing, its date **not confirmed** |
| Volume price, stock, lead time? | Not shown. Lower price columns exist without readable quantity labels. PowerStream says some cells are stocked in Utah, gives 3 to 6 weeks on a sister page, and warns of ocean freight from China for large orders. | **not found** for this part |
| Safety papers? | "UN38.3" is printed against the bare cell. No UL 1642 or IEC 62133 statement was found for it (a different PowerStream cell carries "TUV UL1642"). | VERIFIED as seen; the rest **not found** |
| A second US source in the same size class? | **Not found.** Seen and rejected: SparkFun 40 mAh (about 3.0 mm thick) and TinyCircuits 40 mAh (about 3.5 mm), both sizes taken from `research/power.md` and unverified; Grepow cells at DigiKey (145 mAh and larger; their part codes suggest 2.5 mm or more); Jauch cells at DigiKey (60 mAh and larger; none in a 2 mm thickness appeared). A Chinese maker lists a 201030 cell of 2.2 x 10.5 x 30.1 mm with no US seller. PowerStream's own PGEB021235 (2 x 12 x 35 mm, 40 mAh) is the nearest, from the same seller; it does not fit this board (section 12, item 16). | several listings; VERIFIED only as "none found in the searches made" |

---

## 10. Budgetary cost roll-up

> **This is an estimate for planning, not a costing.** Only 26 % of the 10-unit figure and 14 % of
> the 1000-unit figure come from a price that was seen. Everything marked "assumed" is this study's own guess, made so that the
> columns can be added up; replace each with a quote as it arrives.

### 10.1 Summary

| Cost block | At 10 units (USD per unit) | of which from a price seen | At 1000 units (USD per unit) |
|---|---|---|---|
| Electronic parts and battery | 103.90 | 22.22 | 41.85 |
| Optics, glass, vent, ball feet | 224.75 | 190.65 | 43.30 |
| Tapes and foam (material) | 2.15 | 0.00 | 0.22 |
| Adhesives and primer | 62.80 | 11.30 | 0.80 |
| Bare circuit board | 90.00 | 0.00 | 7.00 |
| Board assembly | 200.00 | 0.00 | 12.00 |
| Base plate (FR-4) | 35.00 | 0.00 | 1.50 |
| 3D printing (tub and baffle ring) | 19.00 | 0.00 | 6.30 |
| Die cutting of the adhesive parts | 80.00 | 0.00 | 1.50 |
| **One marker, parts and outside services** | **817.60** | 224.17 | **114.47** |
| Cradle: electronic parts | 4.83 | 4.32 | 4.22 |
| Cradle: feet and screws | 1.20 | 0.00 | 0.32 |
| Cradle: board and its assembly | 1.70 | 0.00 | 2.60 |
| Cradle: printed body | 40.00 | 0.00 | 12.00 |
| **One consumer cradle** | **47.73** | 4.32 | **19.14** |
| **Marker plus cradle** | **865.33** | 228.49 | **133.62** |

These figures price ten finished FR-4 markers and ten consumer cradles, and nothing else. The EVT programme that the other
two plans describe is larger; section 10.5 prices it.

One-time costs, kept out of the per-unit figures (the mould, not the cookies):

| One-time item | Budget (USD) | Basis |
|---|---|---|
| Assembly fixtures and gauges for EVT (the list in `mechanical/README.md` section 2) | 8,000 to 15,000 | assumed range; no quote. Earlier research gave 1,500 to 5,000 for the pogo fixture and 3,000 to 8,000 for the calibration station, both unverified |
| FCC Part 15B emissions test | 1,500 to 5,000 | range seen on a low-reliability guide site and lab marketing pages; get quotes |
| Production tooling at 1000 units: die-cut tools, glass set-up, production leak tester, test fixtures | not estimated | earlier research gave 200 to 600 per die-cut tool, 500 to 2,000 glass set-up, 8,000 to 20,000 for a leak tester, all unverified |

What ten bare units would cost to place, in round figures (the whole EVT programme is in section 10.5):

| Step | USD |
|---|---|
| 10 markers and 10 cradles at the per-unit figure above | 8,653 |
| Spares and minimum packs: 15 % on the catalogue parts (assumed) | 505 |
| Fixtures and gauges | 8,000 to 15,000 |
| FCC test | 1,500 to 5,000 |
| **Total outlay for ten bare units** | **about 18,500 to 29,000** (rounded) |

Amortised separately, the fixtures add USD 800 to 1,500 to each of 10 units, or USD 8 to 15 to each of 1000 units.

For 1000 units the parts and outside services come to about USD 134,000 for markers with cradles (rounded), before
final-assembly labour, tooling and scrap.

### 10.2 What moves the answer most

| If this changes... | ...the figure moves like this |
|---|---|
| Volume price of the prism (assumed USD 15 each; no source) | at USD 5 each the 1000-unit marker is about USD 94; at Edmund's published 26-49 price of USD 78.50 each it is about USD 241 |
| Board assembly lot charge at 10 units (assumed USD 2,000) | each USD 500 moves the 10-unit marker by USD 50 |
| Bare-board lot charge at 10 units (assumed USD 900) | each USD 300 moves the 10-unit marker by USD 30 |
| Camera price at 10 (USD 27.50 each: reported in earlier research, unverified) | each USD 5 moves the marker by USD 10. The only range seen is USD 6.25 to 44.95: at USD 12 each the marker is USD 31 lower, at USD 44.95 each it is USD 35 higher |
| Battery price at 1000 (assumed USD 5) | moves the marker one for one |

### 10.3 Assumptions

1. **Quantities.** One marker needs the quantities shown in the detail table. Passive part counts (about 30 resistors, 32
   capacitors) are estimates: no netlist or bill-of-materials file for the real board exists yet in `electrical/`.
2. **"At 10" prices** use the published 10-piece price where one was seen; otherwise the 1-piece price where that was seen;
   otherwise an assumption. For parts used many times per marker (LEDs, prisms) the break for the total quantity is used.
3. **"At 1000" prices** use the published 1000-piece (or nearest) price where seen; otherwise an assumption.
4. **Lot charges at 10 units** (bare boards USD 900 for about 20; assembly USD 2,000 for about 12; base plates USD 350 for
   about 30; die cutting USD 800 for about 25 sets) are assumed and divided by 10. No published price for this class of work was seen.
5. **Adhesives at 10 units** are costed as one small pack of each class (USD 20 to 150 each, assumed except one price seen),
   divided by 10. Most of each pack is left over.
6. **Printing** is assumed at USD 15 per tub with dye and vapor smoothing, USD 40 per cradle body, USD 4 of baffle rings per
   marker at 10 units; USD 6, 12 and 0.30 at 1000. Bureau minimum order charges are not included.
7. **Not included anywhere:** final-assembly labour (19 hand steps per marker), test time, yield loss and scrap, packaging, the
   USB cable and charger, freight, sales tax, tariffs, engineering time, and the test equipment that `VALIDATION_PLAN.md` asks
   for (chambers, a reference level, a leak tester, a putting ramp). The per-unit figures also leave out the alternative PA12
   base plate build and the cradles with seven pins; section 10.5 adds them.
8. **Currency.** Where only a euro, pound or Canadian-dollar price was seen, the US-dollar figure used is an assumption, not a
   conversion at a known rate.
9. The EVT build uses the Edmund catalogue prism and the watch-crystal cover glass; the 1000-unit column uses a quoted volume
   prism and a custom strengthened cover glass. That is why those lines show a cost in only one column.
10. The camera price at 10 units (USD 27.50) is the single-piece figure reported in `research/micro-cameras.md`, unverified
    there. The cell price (USD 12.00) is a listing whose date is in doubt (section 9.3). Neither is counted as a price seen.

### 10.4 Line-by-line basis

"seen" means the unit price came from a search result (the row's notes in `sourcing.csv` say where and at what quantity);
"assumed" means it did not. "seen, conflicting" means two extracts disagreed; the higher figure is used and it still
counts as seen. "reported, unverified" is a figure from earlier research that nobody re-checked. "listed, date
unconfirmed" is a listing whose date is in doubt. The last two do not count as a price seen.

| Line | Per | Qty | Each at 10 (USD) | Basis | Each at 1000 (USD) | Basis |
|---|---|---|---|---|---|---|
| Microcontroller | marker | 1 | 7.00 | assumed | 5.00 | assumed |
| Camera cube (2 per marker) | marker | 2 | 27.50 | reported, unverified | 6.25 | assumed |
| Tilt and motion sensor (IMU) | marker | 1 | 4.42 | seen | 3.06 | seen |
| Display (memory LCD, 1.28 inch, 128 x 128) | marker | 1 | 8.82 | seen | 6.77 | seen |
| Display connector (10-way, 0.5 mm pitch, top contact) | marker | 1 | 1.31 | seen | 1.00 | assumed |
| Flash memory (64 Mbit) | marker | 1 | 2.68 | seen, conflicting | 2.13 | seen, conflicting |
| Battery charger chip | marker | 1 | 0.750 | assumed | 0.550 | assumed |
| Always-on 2.8 V regulator | marker | 1 | 0.390 | seen | 0.330 | assumed |
| 3.3 V regulator for the USB supply pin | marker | 1 | 0.450 | assumed | 0.400 | assumed |
| Switchable 2.8 V regulator for the cameras | marker | 1 | 0.400 | seen | 0.300 | assumed |
| USB static-discharge protection | marker | 1 | 0.360 | seen | 0.114 | seen |
| 32.768 kHz crystal (6 pF) | marker | 1 | 0.680 | seen | 0.450 | seen |
| Photodiode (grain reader) | marker | 1 | 2.10 | assumed | 0.950 | assumed |
| Red LEDs, 0402 (8 per marker) | marker | 8 | 0.200 | assumed | 0.080 | assumed |
| Near-infrared LEDs, 0402 (8 per marker) | marker | 8 | 0.310 | seen | 0.240 | seen |
| 220 ohm resistor arrays, 4-in-1 (6 per marker) | marker | 6 | 0.100 | assumed | 0.031 | seen |
| Small N-channel MOSFET | marker | 1 | 0.290 | seen | 0.073 | seen |
| Schottky diode, 30 V 0.5 A | marker | 1 | 0.300 | seen | 0.074 | seen |
| Temperature sensor (10 kohm NTC, 0402) | marker | 1 | 0.090 | seen | 0.030 | assumed |
| Lithium-polymer cell with protection board, 2 x 10 x 30 mm | marker | 1 | 12.00 | listed, date unconfirmed | 5.00 | assumed |
| Chip resistors, 0402 (about 30 per marker) | marker | 30 | 0.030 | assumed | 0.004 | assumed |
| Ceramic chip capacitors, 0402 / 0603 (about 32 per marker) | marker | 32 | 0.040 | assumed | 0.008 | assumed |
| USB-C socket | cradle | 1 | 0.920 | seen, conflicting | 0.600 | assumed |
| Spring pins (4 in the consumer cradle, 7 in the factory fixture) | cradle | 4 | 0.850 | seen | 0.880 | seen |
| Resettable fuse on the 5 V line | cradle | 1 | 0.450 | assumed | 0.100 | assumed |
| 5.1 kohm resistors (2 per cradle) | cradle | 2 | 0.030 | assumed | 0.002 | assumed |
| Fold prism, 2.0 mm (2 per marker) | marker | 2 | 94.50 | seen | - | - |
| Fold prism, production volume source | marker | 2 | - | - | 15.00 | assumed |
| Ball feet, 1.0 mm (3 per marker) | marker | 3 | 0.100 | assumed | 0.100 | assumed |
| Cover glass, EVT (flat mineral-glass watch crystal, 28.0 x 1.0 mm) | marker | 1 | 1.65 | seen | - | - |
| Cover glass, production (chemically strengthened, printed black border) | marker | 1 | - | - | 8.00 | assumed |
| Visor windows, 0.40 mm borosilicate, cut 5.0 x 3.25 mm (2 per marker) | marker | 2 | 15.00 | assumed | 1.50 | assumed |
| Pressure-equalisation vent, adhesive, 5.0 mm | marker | 1 | 3.80 | assumed | 2.00 | assumed |
| Rubber feet for the cradle, about dia 8 x 3 mm (4 per cradle) | cradle | 4 | 0.150 | assumed | 0.050 | assumed |
| Screws, M2 x 5 thread-forming for plastic (4 per cradle) | cradle | 4 | 0.150 | assumed | 0.030 | assumed |
| Adhesive sheet material, circuit board to base plate (FR-4 build) | marker | 1 | 0.500 | assumed | - | - |
| Transfer tape, cover-glass ring (also the sheet of the PA12 build) | marker | 1 | 0.200 | assumed | - | - |
| Adhesive frame for the display, 0.15 mm foam type | marker | 1 | 0.300 | assumed | - | - |
| Opaque black double-coated tape for the baffle annulus, 0.13 mm | marker | 1 | 0.100 | assumed | - | - |
| Cell fixing adhesive, 0.05 mm or thinner | marker | 1 | 0.050 | assumed | 0.020 | assumed |
| Foam pad under the display, 0.3 mm | marker | 1 | 1.00 | assumed | 0.200 | assumed |
| Perimeter seal adhesive (class) | marker | 1 | 8.00 | assumed | 0.150 | assumed |
| Ball-foot potting epoxy (class) | marker | 1 | 4.50 | assumed | 0.050 | assumed |
| Visor-window adhesive, thixotropic light-cure (class) | marker | 1 | 11.30 | seen | 0.100 | assumed |
| Clear optical potting for the grain opening (class) | marker | 1 | 15.00 | assumed | 0.200 | assumed |
| Hood gasket bead, black, soft, silicone-free (class) | marker | 1 | 10.00 | assumed | 0.100 | assumed |
| Cover-glass rim sealant, black, wicking grade (class) | marker | 1 | 4.00 | assumed | 0.050 | assumed |
| Prism bonding adhesive, UV-cure (class) | marker | 1 | 4.00 | assumed | 0.050 | assumed |
| Primer or plasma treatment for the nylon bonding faces (class) | marker | 1 | 4.00 | assumed | 0.050 | assumed |
| Thermal adhesive for the temperature sensor (class) | marker | 1 | 2.00 | assumed | 0.050 | assumed |
| Main circuit board, bare (4 layers, 0.8 mm, ENIG, 0.10 / 0.10 mm in the fine areas, through vias) | marker | 1 | 90.00 | assumed | 7.00 | assumed |
| Circuit-board assembly (both sides, two camera cubes, LGA sensor, 64-pin processor, 0402 parts) | marker | 1 | 200.00 | assumed | 12.00 | assumed |
| Base plate, routed 0.80 mm FR-4, no copper, matte black mask (drawing GL1-011) | marker | 1 | 35.00 | assumed | 1.50 | assumed |
| Cradle circuit board (2 layers, 1.6 mm, 30 x 22 mm) and its assembly | cradle | 1 | 1.70 | assumed | 2.60 | assumed |
| 3D printing of the tub (HP Multi Jet Fusion PA12, dyed black, vapor smoothed) | marker | 1 | 15.00 | assumed | 6.00 | assumed |
| 3D printing of the baffle-ring sets (MJF PA12, dyed black, not smoothed) | marker | 1 | 4.00 | assumed | 0.300 | assumed |
| 3D printing of the cradle body (MJF PA12, not smoothed, not tumbled) | cradle | 1 | 40.00 | assumed | 12.00 | assumed |
| Die cutting of the adhesive parts (patterns GL1-030, -031, -032, -033, -034) | marker | 1 | 80.00 | assumed | 1.50 | assumed |

### 10.5 The whole EVT programme: what the ten-unit figure leaves out

The figures above are like costing a recipe per plate. The kitchen also has to cook the trial portions. The other two
plans ask for much more hardware than ten finished units:

| What | How many | Where it comes from |
|---|---|---|
| Build kits (parts for a complete marker) | 15, to finish 10 | `MANUFACTURING_PLAN.md` 2.1 |
| Units on the printed PA12 base plate | 4 of the 10 (so 6 of the 15 kits) | `MANUFACTURING_PLAN.md` 2.3 |
| Spare assembled boards for the tests before sealing | 8 to 10 (10 used here) | `VALIDATION_PLAN.md` 4.1 |
| Marker shells without working electronics, for destructive tests | 20: 10 with each base plate. Each is a tub with glass, windows, vent and a base plate on a bare or scrap board | `VALIDATION_PLAN.md` 4.1 (PROPOSED there) |
| Dummy markers for the first seating test | 2 | `VALIDATION_PLAN.md` 4.1 |
| Cradles | 12, of which 4 with seven pins | `VALIDATION_PLAN.md` 4.1, tests M1 and M2 |
| Loose cells | 8 | `VALIDATION_PLAN.md` 4.1 |

That makes about 25 assembled boards, about 45 bare boards, about 40 tubs, about 21 FR-4 and 16 PA12
base plates, and about 35 sets of cut tapes in two sheet patterns (40 ordered). This is this report's reading of the two plans. Neither
plan is a parts list, so the counts are **PROPOSED**.

A rough budget for it, built from the same unit figures as section 10.4. Every lot charge is assumed:

| Item | Quantity and unit figure (USD) | Budget (USD) | Basis |
|---|---|---|---|
| Electronic parts for 25 assembled boards (15 builds and 10 spare boards), without cell and display | 25 x 83.08 | 2,077 | as in 10.4 (mixed) |
| Displays (15 builds and 2 shells with displays for the swollen-cell test) | 17 x 8.82 | 150 | seen |
| Cells (15 builds and 8 loose cells) | 23 x 12.00 | 276 | listed, date unconfirmed |
| Prisms (2 per build; 30 pieces fall in Edmund's 26 to 49 price step) | 30 x 78.50 | 2,355 | seen |
| Cover glass, visor windows, vents and ball feet for 15 builds and 20 shells (40 / 80 / 40 / 120 pieces) | 40 x 1.65; 80 x 15.00; 40 x 3.80; 120 x 0.10 | 1,430 | window and vent prices assumed |
| Tape and foam material for 35 | 35 x 2.15 | 75 | assumed |
| Adhesives and primer: two small packs of each class (shells and coupons use them too) | 2 x 628 | 1,256 | assumed, one price seen |
| Bare main boards, one lot of about 45 | lot | 1,800 | assumed (USD 900 for about 20, scaled) |
| Board assembly, 25 boards | lot | 3,600 | assumed (USD 2,000 for about 12, scaled) |
| FR-4 base plates, about 21 needed (GL1-011) | lot of about 30 | 350 | assumed |
| Printed PA12 base plates, about 16 needed (GL1-012) | 20 x 8.00 | 160 | assumed |
| Printed tubs (15 builds, 20 shells, 2 dummies, 3 spare) | 40 x 15.00 | 600 | assumed |
| Baffle-ring sets for the 19 FR-4 builds and shells | 19 x 4.00 | 76 | assumed |
| Die cutting, about 40 sets, now five patterns (GL1-031 added for the PA12 build) | lot | 1,300 | assumed (USD 800 for about 25 sets of four patterns, scaled) |
| Cradles: 12, of which 4 with seven pins for the creep test | 12 x 47.73 + 12 pins | 583 | as in 10.4 (mostly assumed) |
| **EVT programme, parts and outside services** | | **about 16,100** | |

| Step | USD |
|---|---|
| Ten bare units with 15 % spares (section 10.1), for comparison | about 9,200 |
| EVT programme, parts and outside services | about 16,100 |
| Fixtures and gauges | 8,000 to 15,000 |
| **Outlay for the EVT programme, before test equipment and labour** | **about 24,000 to 31,000** (rounded) |

Not in this figure: the test equipment and lab time of `VALIDATION_PLAN.md` (chambers, leak tester, reference level,
putting ramp, the emissions pre-scan), the formal FCC test (it belongs to a later build), labour, freight and tax. Only
16 % of the EVT figure rests on a price seen (the displays and the prisms). Treat it as a size, not a quote.

---

## 11. What could not be verified

1. **Any live stock figure.** Every stock number is an undated extract.
2. **US-dollar prices at 10 and at 1000** for: STM32U585RIT6, OVM7692-RYAA, MCP73831, both MCP1700 parts, VEMD8080, the
   Panasonic resistor array, the red LED, the battery (above quantity 1), the ball feet.
3. **OVM7692:** launch year, any written lifecycle statement, DigiKey price breaks, reflow limits, the pad map.
4. **Sharp display:** the original change notice, whether the panel thickness changes, any statement about this part's future.
5. **Battery:** everything except the listing, the listed size and capacity, and the single-piece price. The date of the
   listing is itself in doubt.
6. **Prism volume source:** no catalogue 2.0 mm aluminised prism at Tower Optical; no volume price anywhere.
7. **Gore vent:** a US distributor, water-entry pressure, IP rating.
8. **Black wicking sealant** for the cover-glass rim: no product found.
9. **Fluorescence** of any clear potting candidate; opacity of any hood-gasket candidate; adhesion of every adhesive to
   vapor-smoothed PA12 and to solder mask.
10. **A black double-coated tape of exactly 0.13 mm**; whether PORON 4790-92 exists at 0.3 mm.
11. **Board fabrication:** via plugging and covering on the underside, matte black mask, a copper-free plate, selective hard
    gold, and any price.
12. **Assembly:** Screaming Circuits and CircuitHub capabilities; any price.
13. **Printing:** Protolabs' MJF tolerance; any US bureau other than those in section 8; any price.
14. **Die cutting:** minimum order, lead time and price at any converter.
15. **Resettable fuse, cradle feet, screws, prism adhesive, primer, thermal adhesive, cell fixing tape, generic resistors and
    capacitors:** not searched line by line; they are common items.
16. **Country of manufacture** for almost every line. Only the Gore vent (Germany, per a distributor listing) was seen; the cell
    maker (China) is an unverified report from earlier research.
17. **Everything worded "reported in review".** This revision could not search or open pages. That covers: which models the
    Sharp change notice touches; the SFH 4053 discontinuation notice and its successor SFH 4053B; the Edmund stock number of
    the 25 x 25 mm window; the date of the PowerStream listing; the second Protolabs wall figure; the layer condition on
    Bay Area Circuits' 4 mil figure; the DigiKey US price of the USB-C socket; the thickness of 3M 467MP and 9471LE; Knight
    Optical's US company; the flash memory's lead time at Future; the Porex IP figures; the date of the Abrisa stock list.
18. **A transfer tape of 0.05 mm or less** for fixing the cell: not searched.

---

## 12. Design items found while sourcing

These are for the design owner. Nothing in `design/`, `mechanical/`, `firmware/`, `sim/` or `electrical/` was edited.

| # | File and place | Finding |
|---|---|---|
| 1 | `design/DESIGN_SPEC.md` section 3 and 4 (grain sensor) | The two grain LED part numbers are not in the specification at all; they exist only in `research/grain-sensing.md` and `research/bom-verification-opto.md`. The infrared one (SFH 4053) is on last-time buy until 31 Jan 2027. Name both parts in the specification and replace the infrared one. The first candidate is the same maker's SFH 4053B (reported as the named successor: PROVISIONAL; confirm footprint, output and a US distributor). |
| 2 | `design/DESIGN_SPEC.md` section 4, "Cell temperature" | NCP15XH103F03RC is flagged "not recommended for new design". Murata's named successor is NCU15XH103F60RC. |
| 3 | `design/DESIGN_SPEC.md` section 4 "PCB" against `electrical/tools/README.md` "Rule set" | The specification says the fine class is 0.10 mm track / 0.10 mm gap; the tool's `US_4L_FINE` rule set says 0.09 / 0.09 mm. At 0.09 mm every US fabricator checked needs its advanced tier. Also, 0.100 mm is 1.6 micrometres under 4 mil (0.1016 mm), and three 4-mil features need 0.3048 mm where a 0.5 mm pitch with 0.20 mm pads leaves 0.300 mm. Ask the fabricator to accept 0.100 mm as "4 mil" in writing, or shrink the pad by 0.005 mm. A review also reports that one fabricator's 4 mil standard figure holds for outer layers only (1 oz inner layers: 5 mil; not re-checked). The specification should say that the fine class is used on the top layer only, or name the inner layers that carry it. |
| 4 | `design/DESIGN_SPEC.md` section 7 | It says the full list of release gates is kept in `docs/RELEASE_GATES.md`. That file did not exist when this report was written. |
| 5 | `design/DESIGN_SPEC.md` section 4 "Rails"; `design/master_params.yaml` `cradle` | Several purchased parts have no part number or rating in the source of truth: the series Schottky diode (only proposed in research), the cradle's resettable fuse (no hold or trip current; PROPOSED here and in `COMPLIANCE.md` row 15: hold about 0.2 A, trip about 0.5 A), the two 5.1 kohm USB-C resistors (not mentioned at all), the cradle feet and screws. There is no cradle schematic. |
| 6 | `design/master_params.yaml` `lcd.glass` (z 4.65 to 5.40); `mechanical/README.md` part list item 3 | A Sharp change notice for this display family reports a new glass supplier (0.5 mm glass only) from December 2024 production and, for some models, a new glass thickness. A polarizer and adhesive change was reported on a sibling part's listing. Neither is confirmed for the LS013B7DH03 (PROVISIONAL). The 0.746 mm panel thickness and the surface that the adhesive frame bonds to should still be re-confirmed on current-production panels. |
| 7 | `design/master_params.yaml` `cover_glass` (thickness 1.0, recess 1.25, 0.12 below flush) | A fabricator's release (dated 2020 according to a review) listed chemically strengthened sheet at 0.8 and 1.1 mm, not 1.0 mm; its later lists are reported to differ. Ask what is stocked near 1.0 mm today, then decide the production thickness and adjust the recess or the tape. Also: `docs/research/display.md` finding 6 advises against sapphire for this window, while the specification and the YAML still allow it. Decide. |
| 8 | `design/master_params.yaml` `visor_window` (5.0 x 3.25 x 0.4) | SCHOTT's own cut-to-size minimum for 0.4 mm D 263 T eco is 10 x 10 mm (tolerance +/-0.2 mm). The window needs a dicing house, and the recess fit (0.25 mm per side) needs that house's tolerance. |
| 9 | `design/master_params.yaml` `vent` | No US source found for VE80205; the 50 kPa water-entry requirement in `research/enclosure-manufacturing.md` is still unconfirmed for it. |
| 10 | `mechanical/README.md` part list item 10 ("1.0 mm stainless balls, grade 25 or better") | The alloy is not specified. The only Grade 25, 1 mm ball found in the US is 440C, which is hard but rusts more readily than 316 in wet, fertilised turf. State the alloy, or add a corrosion test. |
| 11 | `mechanical/README.md` part list item 16 (foam, "Poron 4790 class", 0.3 mm) | Sources disagree on whether 4790-92 is made at 0.3 mm. Choose the grade with a converter. |
| 12 | `mechanical/README.md` part list item 14; `design/master_params.yaml` `baffle.ring.adhesive` ("black double-coated tape 0.13") | No black light-blocking double-coated tape of exactly 0.13 mm was found; 0.10 mm and 0.145 mm exist. The ring is lapped to height, so either works if the number is updated. |
| 13 | `mechanical/README.md` assembly step 12 ("cure at 60 C at most") and section 12 (clear potting) | The recommended cure of one obvious optical epoxy (EPO-TEK 301-2) is 80 C for 3 hours. Choose a room-temperature system, or check what the 23 C alternative cure does to its properties. |
| 14 | `mechanical/README.md` section 12 (perimeter seal) | The work-life requirement (an hour or more) excludes most black structural epoxies sold in small cartridges. Two candidates are named in section 7; the US pack size of one (400 mL, six per case) is awkward for 10 units. |
| 15 | `design/DESIGN_SPEC.md` section 3 ("DigiKey 884-1027-1-ND, in stock") | "In stock" rests on an undated aggregator copy (6,282 pieces, 20-week lead). Treat it as unconfirmed. |
| 16 | `design/master_params.yaml` `battery.body` (34 x 10) | The only near-equivalent cell from the same seller (PGEB021235, 2 x 12 x 35 mm) does not fit this board, and the bay cannot simply grow. The bay already reserves 34 mm for the 30 mm cell with its protection board, so a 35 mm cell needs about 39 mm. The board is only 35.8 mm wide where the rear edge of a 12 mm wide body would lie (board radius 21.1 mm, y = -11.2). The 2 mm of extra width would also use up all but 0.1 mm of the two gaps beside the cell (0.8 mm to the display connector J1, 1.3 mm to the processor). A fallback cell means a new layout with J1 and the processor moved, or a custom cell of the present size. |
| 17 | `electrical/` | There is no netlist, schematic or bill of materials for the real GL-1 board, only the tool and a demonstration board. Passive counts and assembly cost in this report are therefore estimates. |
| 18 | `mechanical/README.md` part list item 20 | The Mill-Max 0914 plunger and barrel diameters are still unconfirmed; the pin itself is VERIFIED in stock at about USD 0.85. |
| 19 | `design/master_params.yaml` `battery.fixing_adhesive_max` (0.05) | The transfer tapes usually named for this job (3M 467MP, 9471LE) are about 0.058 mm (reported; not re-checked). Relax the limit to 0.06 mm, which takes 0.01 mm from the 0.15 mm left above a swollen cell, or name a thinner tape. |
| 20 | `mechanical/README.md` section 2 (part list) | The printed PA12 base plate (GL1-012) and its die-cut sheet (GL1-031) are needed for 4 of the 10 EVT units. This report now carries a line for the plate; no bureau has been asked whether it can hold thickness and flatness on a 0.87 mm plate. |

---

## 13. Sources

All were seen as search-result extracts on 2026-11-11 unless marked otherwise. Sources already listed in
`docs/research/bom-verification-ics.md` and `docs/research/bom-verification-opto.md` are not repeated in full; the rows that
carry their findings forward say so.

Sources attached to a line in the tables:

- https://www.digikey.ca/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579
- https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RYAA/3516559
- https://www.digikey.com/en/products/detail/stmicroelectronics/LSM6DSV16XTR/16841908
- https://www.digikey.com/en/products/detail/sharp-microelectronics/LS013B7DH03/425-2903-ND/5300387
- https://www.digikey.jp/en/products/detail/hirose-electric-co-ltd/FH12A-10S-0-5SH-55/1110331
- https://www.digikey.com/en/products/detail/macronix/MX25R6435FZNIL0/6558605
- https://www.digikey.ca/en/products/detail/microchip-technology/MCP73831T-2ACI-OT/964301
- https://www.digikey.co.za/en/products/detail/microchip-technology/MCP1700T-2802E-TT/5148837
- https://www.digikey.ca/en/products/detail/microchip-technology/MCP1700T-3302E-TT/652676
- https://www.digikey.com/es/products/detail/texas-instruments/LP5907MFX-2-8-NOPB/3906436
- https://www.digikey.co.uk/en/products/detail/stmicroelectronics/USBLC6-2SC6/1121688
- https://www.digikey.ca/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043
- https://azcus.digikey.com/en/products/detail/vishay-semiconductor-opto-division/VEMD8080/8602378
- https://www.findchips.com/search/vlms1500-gs08
- https://www.digikey.com.mx/en/products/detail/ams-osram-usa-inc/SFH-4053/2713572
- https://www.digikey.com.au/en/products/detail/panasonic-electronic-components/EXB-28V221JX/256279
- https://www.digikey.com/en/products/detail/onsemi/BSS138LT1G/918376
- https://azcus.digikey.com/en/products/detail/diodes-incorporated/B0530WS-7-F/816548
- https://www.digikey.com/en/products/detail/murata-electronics/NCP15XH103F03RC/1644666
- https://www.powerstream.com/li-pol.htm
- https://www.digikey.sg/en/products/detail/gct/USB4105-GF-A/11198510
- https://azcus.digikey.com/en/products/detail/mill-max-manufacturing-corp/0914-0-15-20-77-14-11-0/1147053
- https://www.edmundoptics.com/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392/
- https://pmoptics.com/Right_Angle_Prisms.html
- https://www.mcmaster.com/products/balls/diameter~1-mm/
- https://www.esslinger.com/watch-crystal-flat-round-standard-mineral-glass-crystal-1mm-thick/
- https://www.photonicsonline.com/doc/abrisa-technologies-fabricates-coats-corning-gorilla-glass-0001
- https://www.photonicsonline.com/doc/abrisa-technologies-custom-fabricates-and-optically-coats-schott-d-t-eco-ultra-thin-glass-0001
- https://www.gore.com/products/venting/adhesive-vents
- https://3m.com/3M/en_US/p/d/b40072050
- https://catalog.cshyde.com/printitem/3m-products/3m-adhesive-transfer-tapes/3m9472le
- https://tbpconverting.com/wp-content/uploads/2022/02/PDS-3M-5906-5907-5908-5909-TBP-Converting.pdf
- https://www.tesa.com/en/industry/tesa-61361.html
- https://www.stockwell.com/poron-foam-cellular-urethane/
- https://www.3m.com/3M/en_US/p/d/v101722005/
- https://www.chemical-concepts.com/product/aralditer-2031-epoxy-adhesive/
- https://eaa.3m.com/3M/en_US/p/d/b40066483/
- https://ellsworth.com/products/adhesives/epoxy/henkel-loctite-hysol-e-30cl-epoxy-adhesive-clear-200-ml-cartridge
- https://media.focenter.com/CMP1007/files/EPOTEK301SpectrallyTransparentEpoxyRoomTemperatureCure8oz_ET301-8OZ_fiberopticcenter_REV2.pdf
- https://www.testequity.com/product/10000994-6-621-30ML
- https://www.ellsworth.com/products/by-manufacturer/dymax/adhesives/uv-curing/dymax-ultra-light-weld-3094-gel-uv-curing-adhesive-yellow-30-ml-mr-syringe/
- https://products.meridianadhesives.com/storage/downloads/xjagq6xi1luav3sdwj9yuwpee21igy91/301-2-rev-xviii-2.pdf
- https://datasheets.globalspec.com/ds/Master-Bond/ep30-2/bc0f0830-873b-4300-aa6f-c24a19ca3650
- https://dymax.com/products/formulations/light-curable-materials/gasketing
- https://aleo.dymax.com/products/formulations/light-curable-materials/gasketing/ga-112
- https://dymax.com/products/formulations/light-curable-materials/gasketing/ga-142
- https://bayareacircuits.com/pcb-capabilities/
- https://www.macrofab.com/pcba/
- https://www.protolabs.com/services/3d-printing/multi-jet-fusion/
- https://oshpark.com/pricing
- https://3m.com/3M/en_US/converter-solutions-us/applications/prototyping
- https://valleydesign.com/wp-content/uploads/2023/11/schott-d263.pdf
- https://sendcutsend.com/faq/what-is-your-cut-tolerance/
- https://compliancetesting.com/fcc-testing-and-verification/

Further sources used in the text:

- Camera: https://www.findchips.com/detail/ovm7692-ryaa/Omnivision-Technologies-Inc ; https://www.lcsc.com/product-detail/C17590822.html ; https://www.microchipusa.com/product/omnivision-technologies-inc/image-sensors-camera/OVM7692-RACA ; https://www.ovt.com/wp-content/uploads/2026/04/OVM7692-PB-v1.9-WEB.pdf ; https://www.ovt.com/press-releases/omnivision-launches-new-vga-cameracube-device-for-mobile-and-notebook-markets/ ; https://forum.digikey.com/t/camera-cube-lens/17389 ; https://ichome.com/product-detail/omnivision-technologies/ovm7692-ryaa
- Display: https://www.futureelectronics.com/p/6117773 ; https://octopart.com/part/sharp/LS013B7DH03 ; https://ciiva.com/part/ls013b7dh03-7236082 ; https://www.data-modul.com/en/news-events/sharp-ends-industrial-lcd-production-data-modul-ensures-long-term-display-availability ; https://invidis.com/sixteen-nine/2026/02/24/sharp-to-shut-down-kameyama-lcd-plant-after-foxconn-sale-talks-collapse/ ; https://www.data-modul.com/sites/default/files/products/LPM013M126A-specification-12022028.pdf ; https://www.switch-science.com/catalog/2858/
- Battery: https://www.powerstream.com/wp/thin-lithium-ion ; https://hackster.io/products/buy/104896 ; https://www.ainbattery.com/lipo-customized-battery.html ; https://www.sparkfun.com/products/13852 ; https://www.digikey.com/en/products/detail/grepow-inc/GRP363027-1C-3-8V-225mAh-with-PCM/25603135
- Thermistor notice: https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6821/D08401-A-A2127.pdf
- Infrared LED alternatives: https://www.digikey.ca/en/products/detail/inolux/IN-S42CTQIR/10384804 ; https://www.digikey.com.au/en/products/detail/w%C3%BCrth-elektronik/15404085BA420/9857934 ; https://www.digikey.com.au/en/products/detail/rohm-semiconductor/SML-P14RWT86/24634533
- Other electronic parts: https://www.futureelectronics.com/p/semiconductors--microcontrollers--16-bit-general-purpose/stm32u585rit6-stmicroelectronics-8151927 ; https://octopart.com/part/microchip/MCP1700T-2802E%2FTT ; https://octopart.com/part/panasonic/EXB-28V221JX ; https://www.futureelectronics.com/p/3066959 ; https://futureelectronics.com/p/interconnect--ffc-fpc--ffc-fpc-connectors/fh12a-10s-0-5sh-55-hirose-electric-7009729
- Prisms: https://www.knightoptical.com/stock/right-angle-prism-n-bk7-or-equivalent-2x2mm-uncoated-ptk0200 ; https://findlight.net/optics/prisms/right-angle-prisms/tower-optical-laser-grade-prism ; https://edmundoptics.co.uk/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392
- Glass: https://www.photonicsonline.com/doc/high-ion-exchange-hie-glass-solutions-0001 ; https://www.schott.com/en-ae/products/cut-to-size-substrates/technical-details ; https://www.edmundoptics.com/p/25-x-25mm-04mm-thick-schott-d263reg-t-eco-window/45366/ ; https://www.edmundoptics.com/p/5mm-dia-04mm-thick-schott-d263r-t-eco-window/53110/
- Vent: https://uk.rs-online.com/web/p/enclosure-ventilation/2879532 ; https://octopart.com/part/gore/VE80205 ; https://www.porex.com/markets/electronics
- Tapes and foam: https://www.tekra.com/products/adhesives/3m-double-coated-tapes/3m-double-coated-tape-93020le ; https://www.jbc-tech.com/media/w1qirfpp/3m-high-strength-double-coated-tape-93020le-technical-data-sheet.pdf ; https://testequity.com/product/598-884-7000115741 ; https://www.tesa.com/en/industry/tesa-88672.html ; https://www.testequity.com/product/10029445-7100064639 ; https://www.modusadvanced.com/hubfs/Brochures-Guides/Poron-Product-Availability-Booklet.pdf ; https://www.cgrproducts.com/material/poron
- Adhesives: https://multimedia.3m.com/mws/media/2534142O/3m-scotch-weld-epoxy-adhesive-dp490-technical-data-sheet.pdf ; https://www.perigeedirect.com/products/araldite-2031-1-60-min-set-chemical-resistant-black-thixotropic-toughened-epoxy-gel ; https://www.silmid.com/Documents/ARALDITE%202031%20AND%202031-1%20TECHNICAL%20COMPARISON.pdf ; https://www.mouser.com/datasheet/2/773/LOCTITE_EA_E_30CL_en_GL-3433800.pdf ; https://dymax.com/products/formulations/light-curable-materials/bonding/plastic-bonding/3094-gel-rev-a ; the Dymax 3022 series preliminary data sheet (hosted by galindberg.se) ; https://intertronics.co.uk/dymaxgaskets
- Board fabrication and assembly: https://www.protoexpress.com/products/sierra-standard-product/ ; https://www.protoexpress.com/kb/via-covering-in-pcbs/ ; https://www.advancedpcb.com/en-us/resources/manufacturing-capabilities/ ; https://advancedpcb.com/en-us/services/assembly-services ; https://docs.oshpark.com/services/four-layer
- Printing: https://www.protolabs.com/services/3d-printing/vapor-smoothing/ ; https://www.protolabs.com/resources/design-tips/how-to-design-for-nylon-3d-printing/ ; https://fictiv.com/capabilities/processes/multi-jet-fusion ; https://hubs.com/3d-printing/mjf ; https://www.jawstec.com/?p=47757
- Converters: https://info.marianinc.com/adhesive_converter/tape_converter/3m-preferred-converter ; https://strouse.com ; https://www.sur-seal.com/about/3m-preferred-converter/
- FCC test: https://compliancetesting.com/what-is-fcc-part-15b/ ; https://www.compliancegate.com/?p=7230 ; https://markready.pages.dev/guides/fcc-certification-cost (low reliability)

Sources reported by the reviews and **not opened by this revision** (PROVISIONAL until someone reads them):

- Sharp change notice: https://www.futureelectronics.com/p/lcd-display-solutions--displays--passive-matrix-stn-displays/ls011b7dh03-sharp-2105349 ; https://www.futureelectronics.com/p/semiconductors--lcd-display-solutions--displays--active-matrix-tft-displays/ls013b7dh03-sharp-8037364
- Infrared LED: https://www.mouser.com/PCN/ams_OSRAM_OS_PDN_2026_006_ext.PDF ; https://ams-osram.com/products/leds/ir-leds/osram-chip-led-sfh-4053b
- Printing: https://www.protolabs.com/en-gb/services/3d-printing/multi-jet-fusion/
- Board fabrication: https://bayareacircuits.com/wp-content/uploads/2025/12/capabilities.pdf
- USB-C socket, US page: https://www.digikey.com/en/products/detail/gct/USB4105-GF-A/11198441
- Tape thickness: https://www.3m.com/3M/en_US/p/d/b40071696/
- Knight Optical in the US: https://www.laserfocusworld.com/directory/finished-optics-coatings-components/beamsplitters/company/14041874/knight-optical-usa-llc ; https://www.knightoptical.com/stock/prisms/right-angle-prisms/right-angle-prisms-bk7-precision
- Flash memory lead time: https://www.futureelectronics.com/p/5069038

`sourcing.csv` holds 78 rows: the 64 bill-of-materials lines counted above and 14 adhesive candidate rows
(group `2-adhesive-candidate`), which are not counted as lines. Its `notes` column ends with the price basis used in the
roll-up for that line.
