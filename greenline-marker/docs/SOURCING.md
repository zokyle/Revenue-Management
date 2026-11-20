# GreenLine GL-1: where to buy every part in the US (sourcing report)

Design revision: E-EVT1 (amendments E1 to E36; E29 to E34 change the firmware and the user interface only and name no
purchased part). Report revision 4, 2026-11-18: revision 3 of 2026-11-13 (with the corrections of an independent review
made the same day, section 15.2) brought into step with the revision E parts lists of the two boards (section 15.3).
**Revision 4 made no new search and opened no page: every listing, stock figure and price is still the snapshot of
2026-11-13 or 2026-11-11, as each line says.** Companion file: `sourcing.csv` (the same lines, machine-readable).
Revision 2 was dated 2026-11-11; section 15.1 lists what changed since.

> **Nothing in this project has been built or tested, and nothing has been ordered.** This is a buying study done on paper.
> No quote was requested and no sample was handled. Every price and every stock figure is a snapshot taken from a web-search
> extract on 2026-11-13 (or on 2026-11-11 where a line carries that date). No supplier page could be opened from this study,
> so each figure is what the search tool returned from that page, of unknown date. Every price is a budget figure, not an
> offer.

## 1. One-page summary

**VERIFIED** means a US source was seen *listing* the exact part number in a web-search result. It does not mean the item
was on the shelf. For an outside service, which has no part number, it means only that a US company was seen advertising
that kind of work. **PROVISIONAL** means everything else. *Lead time* is how long the factory takes to deliver once a
distributor's shelf is empty. *Life-cycle* is where a part is in its life: active, being phased out, or obsolete. Section 2
explains every other term and the limits of the evidence.

### 1.1 Scoreboard

| Measure | Result |
|---|---|
| Lines in the list: the two boards' parts lists, other purchased parts, material classes, outside services | **86** |
| VERIFIED: a US source was seen listing the exact item | **64 of 86 (74 %)** |
| How fresh: seen on 2026-11-13 / catalogue items carried from 2026-11-11 / outside services carried from 2026-11-11 | 51 / 4 / 9 |
| How firm: a stock figure was seen / listed with no stock figure / outside services, where stock does not apply | 42 / 13 / 9 |
| Of the 42 with a stock figure, lines seen only on an aggregator's copy or a category page, not on a product page | 3 |
| PROVISIONAL: everything else | **22**: 9 adhesive classes with no product chosen, 13 others (no board line: since revision E the two capacitor numbers that could not be bought are replaced) |
| Budget, one marker plus one cradle | about **USD 896** at 10 units and **USD 145** at 1000; 62 % and 70 % of it rest on assumptions |
| Budget, the whole first-build programme (section 10.5) | about **USD 17,000** |

In one sentence: **a US seller was seen listing every line of the two boards' revision E parts lists (the two capacitor
numbers, the fuse, the spring-pin holes and the two amendment parts that revision 3 flagged are corrected in the design);
what remains is that no 4 mm screw has been found for the thinner cradle board, and that three parts with only one maker or
one seller (camera, display, battery cell) still set the schedule.** "Listed" is not "in stock", and a listing says nothing
about a part's pin table or land pattern: those stay PROVISIONAL in the design files.

### 1.2 The three biggest supply risks

1. **Camera cube OVM7692-RYAA**, two per marker. One maker and one authorised US distributor, whose pages showed 1,814 and
   2,497 in stock: about what 1000 markers need, or less. Nothing else fits in its place. Get a written life-cycle statement
   and a quote; buy the cubes for the first two builds now (A10).
2. **Sharp LS013B7DH03 display.** One maker, a 28-week lead time, and shelf stock that is not established: undated copies of
   DigiKey's page ran from 0 to 32,134. Order it before any other part (A11).
3. **Battery cell with protection board.** One US seller, with no stock figure and no lead time; three searches found no
   second one. Ask the seller now for a dated quote, stock and the data sheet (A12).

Section 9 gives the facts behind each risk.

### 1.3 Decisions needed

A1 to A35 are the design actions of section 12.1, where the detail is.

1. **Capacitors.** Done at revision E: the two part numbers are changed (A1, A2) and the status BOM names the 100 nF
   alternate as a candidate (A4). Still open: the loss of capacitance under voltage (A3) and the approval of any alternate
   (A18).
2. **Cradle.** Done at revision E: the fuse is changed and the seven spring-pin holes are corrected (A5, A6). Still open:
   the fuse trips at 0.75 A where amendment E6 says about 0.5 A, and the pin's tail length is an estimate.
3. **Amendments E25 and E26.** Done at revision E: both parts are in the netlist and on the BOM (U12, U11). Still open: the
   stock figures for the E26 part conflict and its order code is not entered (A7, A8).
4. **Infrared LED.** One US distributor showed stock, and its life-cycle reports conflict (A9).
5. **Ball feet.** No US listing with a grade or a price was found for the stainless ball named first. The only priced US
   source found is a silicon nitride ball: USD 2.37 each, about USD 7 per marker (A19).
6. **Prisms.** About USD 189 per marker at 10 units; no volume price is known (section 10.2).
7. **Vent.** No US listing with a price was found; its water-entry pressure has not been seen (A22).
8. **Cover glass.** 1.0 mm is not a stocked thickness of strengthened glass at either US fabricator seen (A28).
9. **Cradle screw and feet.** The model now calls for an M2 x 4 screw (E36); no part number for one has been seen. The
   feet do not match the drawing (A20, A21).
10. **Film and tape.** The sunglasses trial film has no adhesive (A23). The cell tape is 0.058 mm; amendment E22 now allows
    0.06 (A25, closed).
11. **Adhesives.** Three open choices: silicone at the glass rim, the 60 C cure limit, the window adhesive (A30 to A32).
12. **Parts-list files.** Order codes and a column of alternate candidates are on the status BOMs since revision E; no
    alternate is approved yet, and the display and the cell are still on no purchasing list (A11 to A18).

Further down: the count in full (2.1), the cost roll-up (10), what could not be verified (11), a buying order (12.4), and
what changed since revision 2 and in the review (15).

---

## 2. How to read this report

A **bill of materials** (BOM) is the ingredient list of the product: every part and every outside service needed to make one
marker and one charging cradle. This report goes down that list and asks one question per line: *can this exact part be
bought in the US today, from whom, and at what risk?*

**Terms about buying and about the evidence**

| Term | Plain meaning |
|---|---|
| US-sourceable | The exact part number can be bought from a US-based distributor, seller or maker that ships from the US. It does **not** mean "made in USA". Where the country of manufacture was learned it is stated; where it was not, the table says "not found". |
| Part number (MPN) | The maker's exact order code, suffix included. Two codes that differ in one letter can be different parts: several such traps are named in the notes. |
| BOM line, reference | One line of the bill of materials covers every position that uses the same part. The references (C7, R11, U9) are the names printed beside each position on the board; `main-03: C7 C16 ...` means line 3 of the main board's BOM and the positions it covers. |
| Netlist | The list of which pin of which part connects to which. Each board's BOM is generated from its netlist. |
| VERIFIED | A US source listing this exact part number was seen in a web-search result on the date in the Status column. The source and its web address are given, with the stock or lead-time words that were actually seen. VERIFIED means listed for sale. It does not mean in stock, and it is never given from memory. |
| VERIFIED, for an outside service | A service (board fabrication, 3D printing, die cutting, a test laboratory) has no part number. There VERIFIED means only that a US company was seen advertising that kind of work. No company was asked whether it will take this job, and no price was seen. |
| PROVISIONAL | Everything else: no listing was seen, the listing says the part is obsolete or no longer available, the evidence is a data sheet and not an offer to sell, the fact comes from memory, or the design has not chosen a product. It must be confirmed before ordering. |
| Lead time | How long the factory takes to deliver when the distributor's shelf is empty. A 28-week lead time is half a year of waiting. |
| Lifecycle | Where a part is in its life, like a car model: *Active* (in the showroom), *not recommended for new designs* (still built, successor announced), *last-time buy*, also written LTB (final orders by a set date), *obsolete* (gone). |
| Single source | Only one company makes it, or only one sells it. Like a town with one bridge: fine until the bridge closes. |
| Alternate, second source | A part from another maker that can go on the same pads. An *approved* alternate is one the designers have checked and written into the BOM. |
| DNP | "Do not populate": the board has the pads, the part is left off. |
| Aggregator | A website (Findchips, Octopart) that copies distributors' stock and prices. Useful, but its copy can be old. |
| Regional page | The same distributor's site for another country (digikey.ca, digikey.co.uk). It shows the same DigiKey part; the rules of this study accept it as evidence, and the row says so. |
| Punch-out page | A copy of DigiKey's catalogue at an address that begins `punchouttest.digikey`. "Punch-out" is the trade word for a catalogue built into a company's purchasing system. It shows the same DigiKey product, so it counts as a listing, but in this study these pages often said "out of stock" where DigiKey's other pages showed stock. Read its stock words as weak evidence. |
| Category page | A distributor's list of many parts of one kind. A part seen there is listed, but its own product page was not seen. |
| Reel, cut tape, tray | How small parts are packed. A *reel* is a long tape of parts wound on a spool, thousands at a time, for assembly machines. *Cut tape* is a short length cut from a reel, for small orders. A *tray* is a flat moulded carrier for larger chips. One part often has a different order code for each packing. |
| Broker | A trader outside the maker's authorised sales channels. A broker may have stock when the distributors have none, but where its parts came from and how they were stored cannot be traced. |
| Converter | A company that buys tape or foam in wide rolls and cuts it into shaped parts. |
| Quote | No price is published. The supplier prices the job after seeing the drawing. |
| Coupon test | A trial bond on small sample pieces of the real materials, made before an adhesive is chosen. |
| EVT, DVT | Engineering validation test: the first small build, about 10 units. Design validation test: the second, larger build that follows it. |
| Amendment E1 to E36 | The numbered changes at the top of `design/DESIGN_SPEC.md`. E29 to E34 name no purchased part; E35 is a board layout rule and E36 makes the cradle board 1.0 mm (M2 x 4 screws). |

**Technical terms that appear in the tables**

| Term | Plain meaning |
|---|---|
| 0402, 0603, SOT-23, SC-70, SOD-323, LQFP, LGA, WSON, DSBGA | Standard sizes and shapes of part housings ("packages"). An 0402 part is 1.0 x 0.5 mm, about a grain of coarse sand. |
| Pad, footprint, land pattern | A *pad* is the bare metal spot on the board to which one terminal of a part is soldered. The *footprint*, or *land pattern*, is the set of pads and holes drawn on the board for one part. If it does not match the part, the part cannot be soldered on properly. |
| Ball-grid part, ball map | A chip soldered by a grid of tiny solder balls on its underside. The ball map says which ball carries which signal. |
| Dielectric; X5R, X7R, C0G (NP0) | The dielectric is the ceramic inside a capacitor. X5R and X7R are compact kinds whose capacitance drifts with temperature and falls under voltage. C0G, also written NP0, is a stable kind made only in small values. |
| Resettable fuse (PTC); hold and trip current | A fuse that opens when too much current flows and closes again once it has cooled. The hold current is what it carries indefinitely; the trip current is what makes it open. |
| IMU | Inertial measurement unit: the chip that senses tilt and movement. |
| mW/sr | Milliwatts per steradian: how much light an LED sends in one direction. A higher figure is brighter. |
| K (kelvin); B value | A temperature difference of 1 K is the same as 1 C. A thermistor's B value, given in kelvin, says how steeply its resistance changes with temperature. |
| FR-4 | The usual glass-fibre and epoxy sheet that circuit boards are made of. |
| ENIG | A thin gold-over-nickel finish on a board's pads (electroless nickel, immersion gold). |
| Solder mask | The coloured lacquer that covers a board everywhere except its pads. |
| Gerber set | The standard set of files that a board fabricator works from. |
| Reflow | Soldering all the parts of a board at once in an oven. |
| PA12, MJF, vapor smoothing | PA12 is a nylon. MJF (HP Multi Jet Fusion) is a 3D-printing process that fuses nylon powder layer by layer. Vapor smoothing is a chemical treatment that seals and smooths the printed surface. |
| Thixotropic | Stays where it is put, like toothpaste, and flows only while it is being pushed. |
| Viscosity: cP (also written cps), Pa.s | How thick a liquid is. Water is about 1 cP, olive oil about 100 cP, honey several thousand. 1 Pa.s is 1,000 cP. |
| Wick, wicking | Of a liquid: to be drawn into a narrow gap by itself, as ink is drawn into blotting paper. |
| Shore A, Shore 00 | Hardness scales for rubbery materials. Shore A 20 is like a rubber band, A 40 like a pencil eraser, A 90 like the wheel of a shopping trolley. Shore 00 is a scale for softer, gel-like materials. |
| PSA | Pressure-sensitive adhesive: the kind on sticky tape. |
| Birefringent | Said of a material that changes the polarisation of light passing through it. The display's light is polarised, so a birefringent window can show colours or dark patches through polarised sunglasses. |

**How the evidence was gathered.** On 2026-11-13 five research passes each took one slice of the list (active electronics,
passive electronics, the cradle, mechanical parts and films, adhesives and the three supply risks) and searched the web for
each exact part number. Two independent checkers then took the same records, repeated 34 of the claims with 32 searches of
their own, and read 19 more records for whether the quoted evidence really supported the status. Where this report says "the
second check", it means those checkers. Last, an independent reviewer read the finished report against the csv and the
design files and searched again for the two parts that amendments E25 and E26 name (three searches); the corrections that
followed used two more searches to confirm those two listings. Where this report says "the review", it means that step;
section 15.2 lists what it changed.

**How to read the Status column in this revision.**

- VERIFIED means *listed*, not *in stock*. Where a purchased part was listed with no stock figure at all, its stock cell
  begins "stock not seen". That is so for 13 of the 53 VERIFIED purchased-part lines; section 2.1 names them. For the 9
  VERIFIED outside services a stock figure does not apply.
- For an outside service (section 8), VERIFIED means only that a US company was seen advertising that kind of work, on
  2026-11-11. No company was asked whether it will take this job.
- Three VERIFIED lines rest on an aggregator's copy or on a distributor's category page, not on a product page: main-08,
  main-09 and cradle-03. Their notes begin "Evidence grade:".
- Five parts of revision D are no longer on the boards and are kept as history rows in sections 3.1 and 4.1, not as lines:
  the two capacitor numbers that could not be bought (obsolete; no longer available), the cradle fuse that failed amendment
  E25, and the two parts that amendments E25 and E26 replaced. Their Supply-risk cell begins "do not buy" or "superseded".
- The label of a board line (`main-NN`, `cradle-NN`) is its item number in the revision E status BOM. Revision 4 renumbered
  the labels of the main board: revision 3 used the revision D numbers, which were one higher from line 11 on.
- Where the design names no product and this report proposes one, the Part-number cell says "PROPOSED here" and the status
  is that product's. Where the cell says "not selected", the line is PROVISIONAL and the candidates are named beside it.
- Lines dated 2026-11-11 were not checked again. Their evidence is carried from rev 2 so that its age shows; where rev 3
  added a note to such a row, the note says so. Where their notes say "today" or "reported in review", they mean that date
  and the reviews of rev 2.
- Five adhesive candidates dated 2026-11-11 (EPO-TEK 301 and 301-2, Dymax GA-140, GA-112 and GA-142) were moved to
  PROVISIONAL in the review. Their evidence is a data sheet or the maker's own product page, which shows that a product
  exists but is not an offer to sell; rev 2 had counted that as a listing, and the second check had already downgraded the
  foam and one adhesive candidate for the same reason. The candidates that keep VERIFIED rest on a seller's page, or on the
  maker's US catalogue page, for a pack that can be ordered.

**Limits of the evidence. Please read once.**

- Supplier web pages could not be opened. Four attempts were made on 2026-11-13 and all were refused, because the hosts are
  outside this study's allowed network: the Mill-Max drawing (www.mill-max.com, and a copy on assets.rs-online.com), a ball
  maker's grade table (www.thomsonlinear.com) and the cell listing (www.powerstream.com). All web evidence is therefore the
  text that the search tool returned from a page: an extract of unknown date, not the live page.
- Stock and price figures are snapshots. Many come from regional copies of a DigiKey page or from aggregators, and they
  often disagree with each other, sometimes by a factor of thirty on the same day. Each figure names where it was seen. Open
  the live page before you order.
- "Not found" means not found in the searches made, which were few for each part. It does not mean that no seller exists.
  Section 11 lists what was not searched at all.
- Three distributor pages carried notices about US tariffs. No price here includes a tariff.
- The second check re-searched the claims that mattered most; it did not reach everything. Not re-checked by it: the
  microcontroller's price, the tilt sensor's stock, the flash memory's tray and reel codes, the thermistor and its TDK
  alternate, the resistor-array alternate, the cradle feet, the USB-C socket and the cell.
- Hosts that would need to be allowed for a live check: `www.digikey.com`, `www.mouser.com`, `www.arrow.com`,
  `www.newark.com`, `www.futureelectronics.com`, `www.ti.com`, `www.murata.com`, `www.mill-max.com`, `assets.rs-online.com`,
  `www.powerstream.com`, `www.ovt.com`, `www.edmundoptics.com`, `www.mcmaster.com`, `www.thomsonlinear.com`, `www.gore.com`,
  `www.3m.com`, `www.testequity.com`, `www.ellsworth.com`, `www.hisco.com`, `www.bocabearings.com`, `ams-osram.com`,
  `www.porex.com`, and the fabricators' and bureaus' sites named in section 8.

### 2.1 The count in full

Every number in this section, and in the scoreboard of section 1.1, is counted from `sourcing.csv` by the script in
section 14.

| Measure | Result |
|---|---|
| Lines in the list (BOM lines of the two boards, other purchased parts, material classes and outside services) | **86** |
| Lines for which a US source was seen listing the exact item (VERIFIED) | **64 of 86 (74 %)** |
| Of those, lines seen on 2026-11-13 | 51 |
| Of those, catalogue items carried from 2026-11-11 without a new check | 4: Fold prism; Cover glass, EVT; Adhesive sheet material, circuit board to base plate; Transfer tape, cover-glass ring |
| Of those, outside services carried from 2026-11-11 without a new check (for a service, VERIFIED means only that a US company was seen advertising that kind of work) | 9 |
| Of those, purchased parts for which a stock figure was seen | 42 |
| Of those, purchased parts listed with no stock figure at all ("listed" is not "on the shelf") | 13: main-05; main-13; main-16; main-20; main-22; main-37; Lithium-polymer cell with protection board; Ball feet; Cover glass, EVT; Adhesive sheet material, circuit board to base plate; Transfer tape, cover-glass ring; Cell fixing adhesive; Quarter-wave film for the sunglasses trial |
| Of those, outside services, where a stock figure does not apply | 9 |
| Of those, lines whose row rests on an aggregator's copy or a distributor's category page, not on a product page | 3: main-08 (VLMS1500-GS08); main-09 (SFH 4053B); cradle-03 (USB4105-GF-A) |
| Of those, lines for a part that can be bought but that the design must or will replace | 0 (revision 3: 3. B0530WS-7-F, MCP1700T-3302E/TT and MF-FSMF020X-2 are replaced since revision E and are history rows now) |
| Lines still PROVISIONAL | **22** |
| Of those, lines whose part number cannot be bought as named | 0 (revision 3: 2. GRM155R61A105KE15D and GRM155R61A225KE95D are replaced since revision E and are history rows now) |
| Of those, adhesive classes for which the design has not yet chosen a product | 9 |
| Rows in `sourcing.csv` in all (the 86 lines, 24 alternate, candidate or superseded parts, 22 adhesive candidates) | 132: 96 VERIFIED, 36 PROVISIONAL |
| Budget, one marker plus one cradle, at 10 units | about **USD 896** in parts and outside services, before fixtures, test fees and labour. 62 % of it rests on assumptions, 38 % on a price that was seen |
| Budget, one marker plus one cradle, at 1000 units | about **USD 145**, before final-assembly labour, test, scrap and tooling. 70 % of it rests on assumptions |
| Budget, the whole EVT programme of the other two plans (section 10.5) | about **USD 17,000** in parts and outside services |

```
Lines VERIFIED (listed)        [######################........]  64 of 86
  ... with a stock figure seen [###############...............]  42 of 86
10-unit cost from a seen price [###########...................]  38 %
1000-unit cost, seen price     [#########.....................]  30 %
```

How the lines split:

| Group | Lines | VERIFIED | PROVISIONAL |
|---|---|---|---|
| Electronic parts, marker (37 board lines, display, cell) | 39 | 39 | 0 |
| Electronic parts, cradle (7 board lines) | 7 | 7 | 0 |
| Mechanical purchased parts | 9 | 4 | 5 |
| Tapes, film and foam | 8 | 5 | 3 |
| Adhesives (by class; none is selected) | 9 | 0 | 9 |
| Custom parts and outside services | 14 | 9 | 5 |
| **All lines** | **86** | **64** | **22** |
| Alternate, candidate and superseded electronic parts (not lines) | 24 | 18 | 6 |
| Adhesive candidates (not lines) | 22 | 14 | 8 |
| **All rows** | **132** | **96** | **36** |

---

## 3. Electronic parts on the marker

The main board now has a real bill of materials, generated from its netlist (a netlist is the list of which pin of which
part connects to which): `electrical/gl1_main/netlist_out/gl1_main-bom-status.csv`, 37 lines, of which one is not fitted.
The table has one row per line, in the BOM's order, and then the two purchased electronic items that are not on the board's
BOM: the display, which plugs in, and the cell, which is soldered on by hand.

Lines 1 to 7 are capacitors and lines 13 to 25 are resistors: two-ended parts the size of a grain of sand that cost a cent
or so in quantity. A capacitor is a small reservoir of charge; a resistor limits a current. As a class they are the easiest
things on the list to buy. The check of revision 3 turned up two exact numbers, written into the BOM from memory, that could
not be bought as written (one obsolete, one being discontinued). Revision E of the board replaced both (lines 3 and 6), put
the ideal-diode switch U12 in place of the Schottky diode D17 (line 35; D17's old line 10 is gone, which moved lines 11 to
35 of revision D up by one) and made U11 an LP5907 (line 34). The table below is the revision E BOM; the parts that left are
history rows in section 3.1.

Prices are USD per piece. The price column shows a figure only where a US-dollar price was seen at exactly 10 or exactly
1000 pieces; "not seen" means it was not, and the notes under the table give the nearest prices that were seen.

| BOM line | Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|---|
| main-01: C1 C2 C3 C4 C9 C10 C13 C14 C15 C17 C18 C28 C29 C30 C31 C34 | Capacitor 100 nF 16 V X7R 0402 (16 per marker) | GRM155R71C104KA88D | Decoupling capacitors: a small reservoir of charge beside each chip's supply pin, which keeps the supply steady when the chip switches | [DigiKey (490-3261-1-ND); Mouser; Arrow; Newark; Future Electronics; Avnet](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88D/675947) | not seen / 0.00805 | DigiKey: 4,948,426 in stock on one page (a Mexico punch-out page said out of stock; aggregator copies say 3.4 and 12.9 million). Mouser: 6,822,097, factory lead 10 weeks. Future: about 220,000 (global). Standard lead: DigiKey 17 weeks, Arrow 10, Newark 16, Future 30 | medium: stock is deep, but the life-cycle flag conflicts (not recommended for new designs at Octopart, IBS and LCSC; Active at Arrow and Future; Murata's own page not seen), and the part sits in 17 places on the two boards | Samsung CL05B104KO5NNNC (same value, voltage, dielectric and size): VERIFIED, own row | **VERIFIED** 2026-11-13 |
| main-02: C5 C6 | Capacitor 4.7 uF 6.3 V X5R 0402 (2 per marker) | GRM155R60J475ME47D | Bulk capacitors: larger reservoirs on the 2.8 V supply (C5) and on the processor's internal regulator pin (C6) | [DigiKey (regional pages of DigiKey product 3694656: Canada, Brazil, Mexico); Arrow](https://www.digikey.ca/en/products/detail/murata-electronics/GRM155R60J475ME47D/3694656) | not seen / not seen | DigiKey Canada page: 970,727 in stock. Arrow: manufacturer lead 10 weeks (US-shipped source), 16 weeks (Netherlands source) | low | Samsung CL05A475MQ5NRNC: VERIFIED, own row | **VERIFIED** 2026-11-13 |
| main-03: C7 C16 C19 C20 C21 C24 C25 C32 | Capacitor 1 uF 10 V X5R 0402 (8 per marker) | CL05A105KP5NNNC | Input and output capacitors of the two 2.8 V regulators, the cameras' core supply and the analogue supply | [DigiKey (regional pages of DigiKey products 3886734 and 3889162); Avnet Americas; Newark; Future Electronics (factory stock 0)](https://www.digikey.co.za/en/products/detail/samsung-electro-mechanics/CL05A105KP5NNNC/3886734) | not seen / not seen | DigiKey regional pages: Active, 4,480,514 and 3,953,865 in stock (an earlier search snapshot said 692,630); 31-week maker lead on the UK page. Avnet Americas: 2,230,000, 140-week factory lead. Newark: 43,120. Future: factory stock 0, 20 weeks. Mouser: 2,070 in one extract, 0 in an undated aggregator copy | low | Murata GRM155R61C105KA12D, 16 V (PROVISIONAL, own row) | **VERIFIED** 2026-11-13 |
| main-04: C8 | Capacitor 10 nF 50 V X7R 0402 (1 per marker) | GRM155R71H103KA88D | Filters the supply of the processor's analogue section | [Arrow; DigiKey (listing seen on a Mexico punch-out page, DigiKey product 1033252)](https://www.arrow.com/en/products/grm155r71h103ka88d/murata-manufacturing) | not seen / not seen | Arrow: about 4.7 million in total, manufacturer lead 10 weeks (one source) and 14 weeks (another). DigiKey: standard lead 12 weeks, no stock figure in the extract | low | Samsung CL05B103KB5NNNC: VERIFIED, own row | **VERIFIED** 2026-11-13 |
| main-05: C11 C12 | Capacitor 6.8 pF 50 V C0G 0402, +-0.25 pF (2 per marker) | GRM1555C1H6R8CA01D | Load capacitors of the 32.768 kHz clock crystal: they trim its frequency | [DigiKey](https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H6R8CA01D/3693876) | not seen / not seen | stock not seen. DigiKey lists it as active with a 17-week standard lead time | low: a listing was seen, the quantity on hand was not | Yageo CC0402CRNPO9BN6R8 or KEMET C0402C689C5GACTU: both VERIFIED, own rows. Samsung CL05C6R8CB5NNNC: NOT FOUND on seven US distributor sites, do not list it | **VERIFIED** 2026-11-13 |
| main-06: C22 C23 C26 C27 | Capacitor 2.2 uF 10 V X5R 0402 (4 per marker) | GRM155R61A225KE01D | Input and output capacitors of the charger and of the 3.3 V USB regulator | [DigiKey (two product entries, 10695166 and 13544360); Mouser (stock held under the large-reel code GRM155R61A225KE01J)](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A225KE01D/10695166) | not seen / not seen | DigiKey entry 10695166: out of stock, backorder, standard lead 17 weeks (35 pieces of cut tape were shown on the KE01J page); the second entry was not read. Mouser, code KE01J: 47,312 in stock, 50,000 on order | medium: the exact reel code was out of stock at DigiKey in the one entry that was read | Samsung CL05A225KP5NSNC (VERIFIED, own row); Murata GRT155R61A225KE01D (PROVISIONAL, own row) | **VERIFIED** 2026-11-13 |
| main-07: C33 | Capacitor 10 pF 50 V C0G 0402 (1 per marker) | GRM1555C1H100JA01D | Steadies the amplifier that reads the grain photodiode | [Newark (94AK6915); Arrow; DigiKey (listed, out of stock)](https://www.newark.com/murata/grm1555c1h100ja01d/cap-mlc-10pf-c0g-np0-50v-0402/dp/94AK6915) | not seen / not seen | Newark: about 60,000 in stock. DigiKey: out of stock, backorder available. Arrow: stock reported, no figure | low | Samsung CL05C100JB5NNNC: VERIFIED, own row. Murata GRM1555C1H100FA01D (1 %) is DigiKey's suggested upgrade (not checked) | **VERIFIED** 2026-11-13 |
| main-08: D1 D3 D5 D7 D9 D11 D13 D15 | Red LED, 0402 (8 per marker) | VLMS1500-GS08 | Red lights of the experimental grain reader on the underside (the grain reader looks at which way the grass lies) | [Mouser; DigiKey; Future Electronics (all seen through the Findchips aggregator or as result links, not on a distributor's own page)](https://www.findchips.com/search/VLMS1500-GS08) | not seen / not seen | Aggregator copy: Mouser about 57,437; DigiKey about 2,393 with a 12-week lead (a DigiKey Singapore page says 17 weeks) | low: a common part. 1000 markers need 8,000, more than the DigiKey figure; Mouser's covers it | Kingbright APHHS1005SURCK (carried from rev 2, not searched today: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-09: D2 D4 D6 D8 D10 D12 D14 D16 | Near-infrared LED, 0402 (8 per marker) | SFH 4053B | Infrared lights of the grain reader | [Mouser (720-SFH4053B), seen on Mouser category pages only. No DigiKey listing for the B part](https://www.mouser.com/c/optoelectronics/infrared-communications/?mounting+style=SMD%2FSMT&product+type=IR+Emitters+%28IR+LEDs%29) | not seen / not seen | Mouser: 7,096 in stock (other snapshots 6,796, 6,586, 1,888 and, on a regional page, 13,556); factory pack 3,000; marked 'New Product' | medium to high: one US distributor with stock, and the life-cycle evidence conflicts (maker's page: full production; RS: 'currently unavailable' and 'being discontinued by the manufacturer') | Inolux IN-S42CTQIR, the alternative named in the design: VERIFIED at DigiKey, own row; dimmer (5.5 against 9 mW/sr typical at 70 mA) | **VERIFIED** 2026-11-13 |
| main-10: J1 | Display connector, 10-way 0.5 mm, top contact | FH12A-10S-0.5SH(55) | Socket that the display's flexible tail plugs into | [DigiKey (HFK110CT-ND, confirmed 2026-11-13); Future Electronics; Heilind](https://www.digikey.com/en/products/detail/hirose-electric-co-ltd/FH12A-10S-0-5SH-55/1110331) | not seen / not seen | DigiKey: 7,093 in stock, manufacturer lead 12 weeks. Future: 24,000 (global stock), factory lead 20 weeks | low for supply. Design risk: the footprint named in the BOM is the bottom-contact FH12 land pattern, and no extract confirmed that the top-contact FH12A fits it | Same part at Future and Heilind. No drop-in from another maker was searched. Fallback named by amendment E24 if the fold of the display's tail does not fit: a 1.0 mm high back-flip connector about 3.5 mm deep, 'Hirose FH34SRJ-10S-0.5SH class' (not searched: PROVISIONAL; a shallower connector, so a different land pattern) | **VERIFIED** 2026-11-13 |
| main-11: PD1 | Photodiode (grain reader) | VEMD8080 | Light sensor of the grain reader | [Mouser; DigiKey; Arrow; Newark](https://www.digikey.com/en/products/base-product/vishay-semiconductor-opto-division/751/VEMD8080/264846) | not seen / not seen | Mouser 40,449 (another snapshot 25,939); DigiKey 5,900 (another 3,245); Arrow 24,710 (Spanish-language page); Newark 14,670 | low | Sister part VEMD8081 (DigiKey link seen; fit not checked: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-12: Q1 | Small N-channel MOSFET, SOT-23 | BSS138LT1G | A switch that lets the firmware stop charging | [DigiKey (product 918376); Arrow; Mouser](https://www.digikey.com/en/products/detail/onsemi/BSS138LT1G/918376) | not seen / not seen | DigiKey 442,025 in stock (another listing 399,524); Arrow 1,728,620 in total, about 639,620 shipping from the US; Mouser 248,879 in stock and 153,000 on order | low | Same part at Arrow and Mouser | **VERIFIED** 2026-11-13 |
| main-13: R1 | Resistor 10 ohm 1 % 0402 (1 per marker) | RC0402FR-0710RL | With C7 and C8, filters the supply of the processor's analogue section | [Arrow; Mouser; DigiKey (out of stock on the .com page); Newark; Future Electronics](https://www.digikey.com/en/products/detail/yageo/RC0402FR-0710RL/726524) | not seen / not seen | stock not seen as a figure. DigiKey .com: out of stock, backorder; DigiKey Latvia and Netherlands pages: in stock; Arrow: 'large stock', no number; Mouser: listed, factory pack 10,000 | low: one per marker, several distributors | Panasonic ERJ-2RKF10R0X (a Mouser page title only: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-14: R2 R19 | Resistor 10 kohm 1 % 0402 (2 per marker) | RC0402FR-0710KL | R2 holds the processor's start-up mode pin low; R19 is the reference resistor for the processor's cell-temperature measurement | [DigiKey (regional pages of DigiKey product 726523: Mexico, Canada); Arrow; Future Electronics](https://www.digikey.com.mx/en/products/detail/yageo/RC0402FR-0710KL/726523) | not seen / not seen | DigiKey Mexico page: 7,406,426 in stock; DigiKey Canada page: 5,283,844; standard lead 18 weeks | low | Panasonic ERJ-2RKF1002X: VERIFIED, own row | **VERIFIED** 2026-11-13 |
| main-15: R3 R10 R12 R13 R15 R16 R20 R21 R22 R29 R30 | Resistor 100 kohm 1 % 0402 (11 per marker) | RC0402FR-07100KL | Pull-up and pull-down resistors that hold signal lines at a known level, and two voltage dividers | [Mouser; DigiKey; Future Electronics](https://www.mouser.com/en/ProductDetail/YAGEO/RC0402FR-07100KL?qs=mnq%2FyloZIXzTlUn7JAHSWg%3D%3D) | not seen / not seen | Mouser: 3,483,453 in stock, more on order. DigiKey Hong Kong page: about 4.33 million, standard lead 18 weeks | low | Panasonic ERJ-2RKF1003X: VERIFIED, own row | **VERIFIED** 2026-11-13 |
| main-16: R4 R5 | Resistor 1 kohm 1 % 0402 (2 per marker) | RC0402FR-071KL | Protect the two camera power-down lines | [DigiKey; Newark; Avnet; Future Electronics](https://www.digikey.com/en/products/detail/yageo/RC0402FR-071KL/726513) | not seen / not seen | stock not seen. DigiKey lead time quoted as 24 weeks on one listing and 33 weeks on another | low | Panasonic ERJ-2RKF1001X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-17: R6 R7 R8 | Resistor 2.2 kohm 1 % 0402 (3 per marker) | RC0402FR-072K2L | Pull-ups on the cameras' control bus | [Mouser (figure seen on its Norwegian regional page); Newark; DigiKey; Arrow; Avnet (out of stock)](https://www.digikey.com/en/products/detail/yageo/RC0402FR-072K2L/726553) | not seen / not seen | Mouser: 633,136 in stock; Newark: 20,000, standard lead 26 weeks; DigiKey: lead 22 weeks (its Finland page said out of stock, backorder); Avnet: out of stock | low | Panasonic ERJ-2RKF2201X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-18: R9 | Resistor 33 ohm 1 % 0402 (1 per marker) | RC0402FR-0733RL | Tames the clock line that runs from the processor to the cameras | [DigiKey (regional pages: Canada, Mexico); Arrow; Future Electronics](https://www.digikey.ca/en/products/detail/yageo/RC0402FR-0733RL/729540) | not seen / not seen | DigiKey Canada page: 3,237,848 in stock; DigiKey Mexico page: standard lead 17 weeks | low | Panasonic ERJ-2RKF33R0X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-19: R11 | Resistor 6.81 kohm 1 % 0402 (1 per marker) | RC0402FR-076K81L | Sets the charge current to about 20 mA | [Newark (49AK1568); Arrow; DigiKey (listed, out of stock)](https://www.newark.com/yageo/rc0402fr-076k81l/res-6k81-1-0-063w-thick-film-0402/dp/49AK1568) | not seen / not seen | Newark: 7,319 in stock, same-day shipping. Arrow: about 20,000, shipping from the Netherlands, lead 20 weeks. DigiKey: out of stock, backorder (an undated aggregator showed DigiKey 8,538 and Mouser 26,875) | low: one per marker; US shelf stock seen at Newark only | Panasonic ERJ-2RKF6811X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-20: R17 R18 | Resistor 1 Mohm 1 % 0402 (2 per marker) | RC0402FR-071ML | Divider that lets the processor measure the cell voltage | [DigiKey; Avnet; Newark](https://www.digikey.com/en/products/detail/yageo/RC0402FR-071ML/726515) | not seen / not seen | stock not seen (listing only) | low | Panasonic ERJ-2RKF1004X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-21: R23 R24 R25 R26 R27 | Resistor 68 ohm 1 % 0402 (5 per marker) | RC0402FR-0768RL | Set the current of the grain reader's LEDs | [DigiKey (311-68.0LRCT-ND cut tape, 311-68.0LRTR-ND reel); Future Electronics](https://www.digikey.com/en/products/detail/yageo/RC0402FR-0768RL/726652) | not seen / not seen | DigiKey regional pages (two product entries, 726652 and 729599): about 115,000 to 341,000 in stock, lead 17 weeks; one DigiKey extract said 106 in stock with a 22-week lead. Future: 180,000 (global), minimum 10,000, factory lead 26 weeks | low | Panasonic ERJ-2RKF68R0X (searched, no listing surfaced), Vishay CRCW040268R0FKED, Stackpole RMCF0402FT68R0 (from memory): all PROVISIONAL | **VERIFIED** 2026-11-13 |
| main-22: R28 | Resistor 470 kohm 1 % 0402 (1 per marker) | RC0402FR-07470KL | Sets the gain of the amplifier that reads the grain photodiode | [DigiKey; Newark; Future Electronics (specification page)](https://www.digikey.com/en/products/detail/yageo/RC0402FR-07470KL/726618) | not seen / not seen | stock not seen today. DigiKey: lead 22 weeks; the only figures are from an aggregator dated 2026-06-07 (DigiKey 278,900; Newark 10,000) | low | Panasonic ERJ-2RKF4703X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-23: R31 | Resistor 150 kohm 1 % 0402 (1 per marker) | RC0402FR-07150KL | Holds the photodiode's wake line high in the dark | [DigiKey; Arrow; Avnet](https://www.digikey.com/en/products/detail/yageo/RC0402FR-07150KL/726542) | not seen / not seen | DigiKey: 538,883 in stock, standard lead 18 weeks | low | Panasonic ERJ-2RKF1503X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-24: RN1 RN2 RN3 RN4 RN5 RN6 | Resistor array 4 x 220 ohm, 0804 (6 per marker) | EXB-28V221JX | Protect the camera data wires that the two cameras share | [DigiKey (Y7221CT-ND cut tape, Y7221TR-ND reel; figures from its Australia and Mexico pages); Arrow](https://www.digikey.com.au/en/products/detail/panasonic-electronic-components/EXB-28V221JX/256279) | not seen / not seen | DigiKey Australia page: 72,722 in stock; DigiKey Mexico punch-out page: out of stock, backorder; standard lead 18 weeks | low | Yageo YC124-JR-07220RL: VERIFIED, own row (compare land pattern and height first). Bourns CAY10-221J4LF: not confirmed (a page title on DigiKey's Mexico site, then not found when searched directly: PROVISIONAL). 'Bourns CAT16', named in rev 2, is a larger array that would not fit the pads (from memory): dropped | **VERIFIED** 2026-11-13 |
| main-25: RT1 RT2 | Temperature sensor: NTC thermistor 10 kohm 1 %, 0402 (2 per marker) | NCU15XH103F60RC | Sit beside the cell: one tells the charger, the other tells the processor, whether the cell is too hot or too cold | [DigiKey (490-18149-1-ND cut tape, 490-18149-2-ND reel); Newark; Mouser (aggregator copy only); Arrow (no stock)](https://www.digikey.com/en/products/detail/murata-electronics/NCU15XH103F60RC/9686714) | not seen / not seen | DigiKey US page: about 74,858 in stock in one extract, 55,871 in another, standard lead 17 weeks (its Mexico and Germany pages said 0). Newark: about 8,204. Mouser (aggregator copy): 50,000. Arrow: no stock, minimum 10,000 | low | TDK NTCG103JF103FT1: VERIFIED, own row (compare the resistance-temperature table first) | **VERIFIED** 2026-11-13 |
| main-26: U1 | Microcontroller, LQFP-64 | STM32U585RIT6 | The single processor: runs the cameras, tilt sensor, display, USB and the putt maths | [DigiKey (497-STM32U585RIT6-ND); Future Electronics (zero stock)](https://www.digikey.com/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579) | not seen / not seen | Conflicting. DigiKey US page: 4,437 in stock, manufacturer lead 52 weeks. DigiKey regional pages: 409 (Austria), 554 (UK), 223 (Lithuania), several at 0, lead 13 weeks. Future: 0 in stock, 13-week factory lead, tray of 160 | medium: only DigiKey shows stock, and its price and lead time differ from page to page | STM32U575RIT6 (same package; pin compatibility from memory: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-27: U2 U3 | Camera cube (2 per marker) | OVM7692-RYAA | The two forward-looking eyes (640 x 480 pixels each); a camera cube is a complete camera, sensor and lens, in one block a few millimetres across | [DigiKey only (884-1027-1-ND on cut tape; reel of 2,500). Arrow has a catalogue page with no stock or price. No Mouser, Newark, Avnet or Future listing](https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RYAA/3516559) | not seen / not seen | DigiKey's own pages, undated: 1,814 in stock on one and 2,497 on another; manufacturer lead 14 weeks; standard package 2,500. An aggregator shows 6,282 with a 20-week lead; that figure is close to a broker's and may not be DigiKey's | high: one maker, one authorised US distributor, no drop-in alternative; 1000 markers need 2,000 cubes plus losses, more than either DigiKey snapshot | None that drops in: OVM7692-RAAA is a different size and OVM7692-RACA is listed obsolete. Otherwise brokers only (Quest Components 1,557 pcs; Vyrian about 6,152; Microchip USA; PCX): not a safe source for an optical part | **VERIFIED** 2026-11-13 |
| main-28: U4 | Tilt and motion sensor (IMU), LGA-14 | LSM6DSV16XTR | Measures the slope under the marker and wakes it when it is moved | [Newark (62AK1744); Mouser; Arrow; DigiKey (listed, out of stock)](https://www.newark.com/stmicroelectronics/lsm6dsv16xtr/inemo-inertial-module-3-6v-smd/dp/62AK1744) | not seen / not seen | Newark 5,212 in stock; Mouser 5,775 (another row: 19,537 with an expected date in 2027); Arrow 41 now and 10,000 at a 5,000 minimum; DigiKey: out of stock, backorder | low to medium: one maker; out of stock at the distributor the BOM names | Same part at Mouser and Arrow. LSM6DSVTR (same family) would need a firmware change (PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-29: U6 | Flash memory 64 Mbit, 8-WSON (tray code) | MX25R6435FZNIL0 | Stores logged camera frames, calibration and settings | [Arrow (seen on its French-language page for this exact number); DigiKey (prices only, no stock figure today)](https://www.arrow.com/fr-fr/products/mx25r6435fznil0/macronix-international) | not seen / not seen | Arrow (French page): 3,200 pieces ready to ship next day. DigiKey: no stock count seen today (snapshots ran from 0 to about 65,000 on 2026-11-11) | medium: the stock evidence for the tray code is thin; Arrow US and Mouser show stock for the reel code | Tape-and-reel code of the same chip, MX25R6435FZNIL0 TR: VERIFIED, own row | **VERIFIED** 2026-11-13 |
| main-30: U7 | Always-on 2.8 V regulator, SOT-23 | MCP1700T-2802E/TT | Feeds the processor, tilt sensor and display with very little standby drain | [DigiKey (MCP1700T-2802E/TTCT-ND); Mouser; microchipDIRECT](https://www.digikey.com/en/products/detail/microchip-technology/MCP1700T-2802E-TT/MCP1700T-2802E-TTCT-ND/5148837) | not seen / not seen | DigiKey 13,977 in stock; Mouser 6,319; microchipDIRECT 42,689 | low | Same part at Mouser and microchipDIRECT | **VERIFIED** 2026-11-13 |
| main-31: U8 | Switchable 2.8 V regulator for the cameras, SOT-23-5 | LP5907MFX-2.8/NOPB | Low-noise supply that is switched on only during a read | [DigiKey (product 3906436); Arrow; TI store (out of stock)](https://www.digikey.com/en/products/detail/texas-instruments/LP5907MFX-2-8-NOPB/3906436) | not seen / 0.29 | DigiKey about 78,510 in stock (another snapshot 77,470), manufacturer lead 9 weeks; Arrow 873, ships next day; TI store: out of stock | low | Same part at Arrow | **VERIFIED** 2026-11-13 |
| main-32: U9 | Battery charger chip, DSBGA-6 | BQ25101YFPR | Charges the cell at about 20 mA, and stops by itself when the cell is too hot or too cold | [DigiKey (296-39933-1-ND cut tape, 296-39933-2-ND reel; regional pages); Mouser (595-BQ25101YFPR); Arrow; TI store (out of stock)](https://www.digikey.ca/en/products/detail/texas-instruments/BQ25101YFPR/5022365) | not seen / not seen | DigiKey (regional pages): Part Status Active, maker lead 12 weeks; an aggregator copy shows 4,010 under 296-39933-1-ND. Mouser: 5,558 in stock (read from a series page that also covers sister codes). Arrow: 1,840 shipping next day (US page), 12-week maker lead | low to medium: one maker; a 0.4 mm ball-grid part whose ball map is confirmed only from third-party copies of the data sheet | Same part at Mouser and Arrow. Fallback on the same footprint, BQ25100YFP: not searched (PROVISIONAL) | **VERIFIED** 2026-11-13 |
| main-33: U10 | USB static-discharge protection, SOT-23-6 | USBLC6-2SC6 | Protects the USB and power contacts from static shocks | [DigiKey (497-5235-1-ND); Arrow; Newark](https://www.digikey.com/en/products/detail/stmicroelectronics/USBLC6-2SC6/1121688) | 0.243 / 0.114 | DigiKey about 113,703 in stock; Arrow 18,492, about 17,932 of them shipping from the US; Newark about 138,000 | low | Same part at Arrow and Newark | **VERIFIED** 2026-11-13 |
| main-34: U11 | 3.3 V regulator with enable for the USB supply pin, SOT-23-5 | LP5907MFX-3.3/NOPB | Powers the processor's USB pin; only live in the cradle, and held off until the main 2.8 V supply is up (E26) | [DigiKey (product entries 3906441 and 5034443; reel 296-38557-2-ND; regional pages only: the US page was in no result); Mouser (price only, through an aggregator)](https://www.digikey.co.uk/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/5034443) | not seen / not seen | CONFLICTING between regional DigiKey pages: UK 4,013 in stock (entry 5034443); Switzerland 11,506; Denmark 44,232; Germany 108,067; Australia, Canada and Austria: out of stock, backorder. Standard lead 12 weeks. Aggregator copy: DigiKey 2,031 | low to medium: listed, and in the family already used for U8, but its stock was seen only on regional pages that disagree (from none to about 108,000) | none checked | **VERIFIED** 2026-11-13 |
| main-35: U12 | Ideal-diode switch, SC-70-6 | LM66100DCKR | An electronic one-way valve with almost no voltage loss between the cradle's 5 V contact and the charger (E25; it replaced the Schottky diode D17 of rev D) | [DigiKey (product 10273183; cut tape 296-53541-1-ND, reel 296-53541-2-ND); Mouser (595-LM66100DCKR, through aggregator copies only)](https://www.digikey.com/en/products/detail/texas-instruments/LM66100DCKR/10273183) | not seen / not seen | DigiKey US page: 53,573 in stock (the same figure in three searches). Regional DigiKey pages: from 13,653 (Canada) and 14,273 (Mexico) to 66,618 (Italy, Singapore); a Canada punch-out page: 0; standard lead 12 weeks (6 weeks on one aggregator copy). Aggregator copies: DigiKey 60,934; Mouser 49,753 and 41,034; one of 150,861 with no seller named | low for supply: deep stock was seen at DigiKey and the part is listed as Active. Its pin table and the polarity of its enable pin, as used in the netlist, are PROVISIONAL until the data sheet is read (a design gate, not a supply risk) | none checked: no second maker's part for the same pads was searched | **VERIFIED** 2026-11-13 |
| main-36: Y1 | 32.768 kHz crystal, 3.2 x 1.5 mm | ABS07-120-32.768KHZ-T | Keeps time and paces the display refresh while the marker sleeps | [DigiKey (product 3724043); Newark (56AC7523); Arrow](https://www.digikey.com/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043) | not seen / not seen | DigiKey 76,840 in stock (another page 74,441), manufacturer lead 20 weeks; Newark 17,458; Arrow about 578,309 in total | low | Same part at Newark and Arrow | **VERIFIED** 2026-11-13 |
| main-37: R14 (DNP) | Resistor 6.04 kohm 1 % 0402 (not fitted) | RC0402FR-076K04L | An empty position on the board, used only if the fallback charger chip is ever fitted | [DigiKey; Arrow; Newark](https://www.digikey.com/en/products/detail/yageo/RC0402FR-076K04L/2345144) | not seen / not seen | stock not seen (listing only) | low: not fitted, none is bought | Panasonic ERJ-2RKF6041X (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| off-board: plugs into main J1 (not a line of the board BOM) | Display (memory LCD, 1.28 inch, 128 x 128) | LS013B7DH03 | Shows the aim line; readable in sunlight; uses almost no power | [DigiKey (425-2903-ND); Arrow (seen on its Mexico page); Future Electronics (zero stock, minimum 2,240). Mouser does not sell it](https://www.digikey.com/en/products/detail/sharp-microelectronics/LS013B7DH03/425-2903-ND/5300387) | 9.60 / not seen | NOT ESTABLISHED. Undated DigiKey captures seen today: 0 in stock with a 28-week lead on one; 206, 5,233, 5,674, 10,863, 27,098, 27,144 and 32,134 on others (the US page said 0 on 2026-11-11). Arrow: about 1,383, ships in 2 days. Future: 0, factory lead 28 weeks, minimum 2,240 | high: one maker, no drop-in second source, 28-week factory lead, shelf stock not established | None that drops in. Sharp LS013B7DH06 is larger (26.82 x 31.3 mm against 26.6 x 30.3 mm) and listed obsolete at Octopart | **VERIFIED** 2026-11-13 |
| off-board: soldered to main BT1 BT2 (not a line of the board BOM) | Lithium-polymer cell with protection board, 2 x 10 x 30 mm, 43 mAh | GM201030-PCB | The rechargeable battery | [PowerStream Technology, Utah (direct). No other US seller found](https://www.powerstream.com/li-pol.htm) | not seen / not seen | stock not seen: no count and no lead time. The listing has an 'Add to Cart' button; the site says such cells 'are in stock for sample quantities' and that it tries to keep 5 to 500 pieces. One extract dates the page 27 September 2024 | high: one seller, no second US source found in this size (three searches); price and availability unconfirmed | None that fits. AIN Battery AIN201030 (China; 2.2 x 10.5 x 30.1 mm, no protection board stated) shows only that the size exists at a second maker. PowerStream's PGEB021235-PCB does not fit the board (section 12.2) | **VERIFIED** 2026-11-13 |

Country of manufacture: not found for the lines above, except: Lithium-polymer cell with protection board, 2 x 10 x 30 mm, 43 mAh: China (cell maker reported in docs/research/power.md, unverified).

Notes on these lines:

- **Capacitor 100 nF 16 V X7R 0402 (16 per marker)** (main-01): Lifecycle: conflicting. DigiKey USD prices: 0.10 at 1, 0.00805 at 1,000. A 'suggested alternate' quoted by one site (GRM033C71C104KE14D) is an 0201 part and not a drop-in. The same part is C1 on the cradle. Design action A4.
- **Capacitor 4.7 uF 6.3 V X5R 0402 (2 per marker)** (main-02): Lifecycle: Active (Arrow). Evidence is from regional DigiKey sites showing the same DigiKey product, plus arrow.com. USD prices seen: 0.12 at 1, 0.02898 at 500. Tolerance is 20 %. Loss of capacitance under working voltage: design action A3.
- **Capacitor 1 uF 10 V X5R 0402 (8 per marker)** (main-03): Lifecycle: Active (DigiKey regional page). DigiKey's title: '1 uF +-10% 10V Ceramic Capacitor X5R 0402 (1005 Metric)'. Newark: about 0.10 at 1. Name DigiKey and Avnet as the sources; do not count on Mouser. Evidence is from regional DigiKey sites; the US page was not in the results. The line 'DigiKey lists it as the direct substitute' was not re-seen (one extract names a KEMET part instead). It loses capacitance under voltage just as the part it replaces does. Rev E: this is the part on the BOM (design action A1 applied in electrical/gl1_main); it replaced Murata GRM155R61A105KE15D, which is obsolete (history row in section 3.1). Loss of capacitance under working voltage: A3.
- **Capacitor 10 nF 50 V X7R 0402 (1 per marker)** (main-04): Lifecycle: Active (Arrow). No price seen.
- **Capacitor 6.8 pF 50 V C0G 0402, +-0.25 pF (2 per marker)** (main-05): VERIFIED means a listing for the exact number was seen, not that the part is on the shelf. An aggregator line with stock and prices was tied to the large-reel code ...CA01J and is not used here. Researcher's design remark: two 6.8 pF in series give 3.4 pF plus stray against the crystal's 6 pF load figure. No price seen.
- **Capacitor 2.2 uF 10 V X5R 0402 (4 per marker)** (main-06): The D at the end is the 10,000-piece reel and J the 50,000-piece reel of the same capacitor. A cut-tape price of 0.11 was seen, quantity not stated. Read both DigiKey entries before concluding that it is out of stock. Lifecycle not seen. That KE01D succeeds KE95D is an inference, not a statement seen: DigiKey names GRM155R61A225ME01D as the substitute for the obsolete 20 % sibling GRM155R61A225ME95D. Confirm it. Rev E: this is the part on the BOM (design action A2 applied in electrical/gl1_main); it replaced GRM155R61A225KE95D (history row in section 3.1). The value itself, 2.2 uF at C22, C23, C26 and C27, is amendment E27. Loss of capacitance under working voltage: A3.
- **Capacitor 10 pF 50 V C0G 0402 (1 per marker)** (main-07): No price seen for the Murata part.
- **Red LED, 0402 (8 per marker)** (main-08): Evidence grade: aggregator copy, not a distributor page; spend one search on a distributor page before the order. Prices seen: DigiKey about 0.33 at 1 falling to about 0.12 at 100; Mouser about 0.055 to 0.34 depending on quantity. Lifecycle not seen. Pad layout and polarity mark not checked.
- **Near-infrared LED, 0402 (8 per marker)** (main-09): Evidence grade: distributor category pages, not a product page. Lifecycle: conflicting. VERIFIED here means that a listing for the exact number was seen on Mouser category pages (US and regional); no Mouser product page came up. Prices seen at Mouser: 0.62 at 1 (one snapshot 0.58), about 0.25 at higher quantities, 0.206 at 3,000 on reel; a possible US tariff surcharge is mentioned. Wavelength is 850 nm on the maker's English page and on Mouser, 860 nm on RS and on the maker's Japanese page. The maker gives 1.0 x 0.5 x 0.45 mm; no extract said '0402' for the B part. Maker's ordering code Q65115A1586; 5.6 to 11.2 mW/sr, 9 typical, at 70 mA. Replaces the SFH 4053 of rev 2 (amendment E3). Design action A9.
- **Display connector, 10-way 0.5 mm, top contact** (main-10): DigiKey's title says 'Contacts, Top'; Future says 'Top Contact'; Heilind lists the contact orientation as 'top'. Prices seen: DigiKey 1.22 at 1, 0.70801 at 14,000; Future 0.68 at 2,000 or more. Keep the letter A and the (55) suffix: DigiKey marks the un-suffixed FH12A-10S-0.5SH obsolete, and FH12-10S-0.5SH(55), which is what Mouser returned, is the bottom-contact part. The 2.0 mm height was not seen. Amendment E24 moved J1 0.5 mm toward the rear and names a fallback connector (Hirose FH34SRJ-10S-0.5SH class); no listing for that part has been looked for. Design action A15.
- **Photodiode (grain reader)** (main-11): Prices seen: Mouser 1.86 at 1, about 1.11 at higher quantity; DigiKey 2.36 at 1, 0.97158 at 5,000; Arrow about 1.01 in small quantity. Newark's page carries its 'No longer stocked / No Longer Manufactured' flag although it shows stock. The land pattern in the BOM is a provisional stand-in: take the pads from the Vishay drawing.
- **Small N-channel MOSFET, SOT-23** (main-12): Prices seen today: DigiKey 0.34 at 1, 0.06449 at 3,000 on reel; Mouser 0.42 at 1 (its page says a tariff of 8 % may be applied on shipments to the United States). On 2026-11-11: 0.0734 at 1,000 at DigiKey. Newark's result was BVSS138LT1G, a different (automotive) number. The DigiKey order code and the 1.5 V maximum gate threshold were not seen.
- **Resistor 10 ohm 1 % 0402 (1 per marker)** (main-13): VERIFIED means the listing was seen; no stock figure. No USD price seen (about EUR 0.09 to 0.10 for one).
- **Resistor 10 kohm 1 % 0402 (2 per marker)** (main-14): USD 0.10 at 1 seen; the 1,000-piece price seen is in Canadian dollars (0.00798).
- **Resistor 100 kohm 1 % 0402 (11 per marker)** (main-15): Only the 10,000-piece reel price was seen (0.00127 at DigiKey); 1000 markers need 11,000.
- **Resistor 1 kohm 1 % 0402 (2 per marker)** (main-16): Lifecycle: Active (DigiKey). VERIFIED means the listing was seen; quantity on hand and price were not.
- **Resistor 2.2 kohm 1 % 0402 (3 per marker)** (main-17): Lifecycle: active (search summary). No price seen.
- **Resistor 33 ohm 1 % 0402 (1 per marker)** (main-18): No USD price seen.
- **Resistor 6.81 kohm 1 % 0402 (1 per marker)** (main-19): No price seen.
- **Resistor 1 Mohm 1 % 0402 (2 per marker)** (main-20): VERIFIED means the listing was seen at three US distributors; stock, price and status were not in the extract.
- **Resistor 68 ohm 1 % 0402 (5 per marker)** (main-21): Lifecycle: Active (DigiKey); Octopart shows it in production at six authorised distributors. The researcher's 'thin stock' alarm (106 pieces) was refuted by the second check; the DigiKey US page itself was in neither set of results. Do not confuse with RC0402FR-0768KL (68 kohm) or RC0402FR-07680RL (680 ohm). No price seen.
- **Resistor 470 kohm 1 % 0402 (1 per marker)** (main-22): Lifecycle: active (search summary). No price seen.
- **Resistor 150 kohm 1 % 0402 (1 per marker)** (main-23): Lifecycle: active (search summary). No price seen.
- **Resistor array 4 x 220 ohm, 0804 (6 per marker)** (main-24): The DigiKey number in the BOM is correct. Same two conflicting stock snapshots as on 2026-11-11. Octopart showed 0.031 on 2026-11-11 (quantity not stated; reel of 10,000). The match of height and land pattern against the Panasonic drawing is still open.
- **Temperature sensor: NTC thermistor 10 kohm 1 %, 0402 (2 per marker)** (main-25): Lifecycle: active (Octopart: in production). B 3380 K is the B(25/50) figure; distributors that quote 3434 K are quoting B(25/85) of the same part. Prices seen: about 0.037 at 10,000 falling to about 0.030 at 250,000 (DigiKey US). Look-alikes that are not this part: NCU15XH103J60RC, NCU15XH103E60RC, NCU15XH103D6SRC, NCU15XH103F6SRC. The resistance-temperature table has still not been read against the charger's thresholds. Replaces the NCP15XH103F03RC of rev 2 (amendment E2). The BOM's Distributor PN cell can be filled: 490-18149-1-ND.
- **Microcontroller, LQFP-64** (main-26): Prices seen: DigiKey US 12.16 at 1 falling to 7.52 at 500; DigiKey regional pages EUR 8.09 at 1 and EUR 4.87 at 960; Future 4.83 at 160 or more. Rev 2 assumed 7.00 at 10. No Mouser or Arrow listing for this exact part came up. Do not order STM32U585RIT6Q: a different pin-out (DigiKey US 743 in stock, 9.37 at 1). Lifecycle not seen. Design action A16.
- **Camera cube (2 per marker)** (main-27): Lifecycle: Active (DigiKey 'Part Status Active'); Findchips gives 'Contact Manufacturer'. No end-of-life, last-time-buy or change notice was found in two independent searches; no statement from the maker was seen either. Prices seen on DigiKey's own page: 27.50 at 1 on cut tape, 6.25 at 2,500 on reel; no break in between. The ball map in the BOM is a provisional stand-in. Section 9.1; design action A10.
- **Tilt and motion sensor (IMU), LGA-14** (main-28): Prices seen: 5.75 at 1 (Newark and DigiKey), 3.71 at 5,000 (Newark); Arrow 4.4285 for its 41 pieces and 2.749 at 5,000. The BOM says DigiKey at 4.42. Lifecycle not seen. Design action A13.
- **Flash memory 64 Mbit, 8-WSON (tray code)** (main-29): Evidence is a regional page of a US distributor showing the same part. Prices seen: Arrow France 1.3946 (currency not stated); DigiKey snippets 1.94 and 3.37 with no quantity. The roll-up uses the reel code's prices. Lifecycle not seen. Design action A14.
- **Always-on 2.8 V regulator, SOT-23** (main-30): Prices seen: DigiKey 0.39 at 3,000; Mouser 0.51 at 1. The 2.8 V output is read from the '2802' in the code, not from an extract. The BOM's Distributor PN cell can be filled: MCP1700T-2802E/TTCT-ND. Lifecycle not seen.
- **Switchable 2.8 V regulator for the cameras, SOT-23-5** (main-31): Prices seen today: DigiKey 0.62 at 1, about 0.29 at 1,000, 0.277 at 3,000 on reel; Arrow 0.3099. On 2026-11-11: 0.402 at 10. The BOM says 0.65. DigiKey order code not seen. Lifecycle not seen.
- **Battery charger chip, DSBGA-6** (main-32): Lifecycle: Active (DigiKey, Arrow). Prices seen: Mouser 1.61 at 1 on cut tape, reel from 0.761; Arrow 1.0745. A figure of 0.913 at 1,000 was handed to this study as a DigiKey figure; neither the researcher nor the checker saw it. DigiKey: charge current 250 mA maximum, 4.2 V. An Arrow French page shows no stock and a 35-week lead, so Arrow's stock is regional. Do not order BQ25101HYFPR (a different part). The BOM's Distributor PN cell can be filled: 296-39933-1-ND. Replaces the MCP73831T-2ACI/OT of rev 2 (amendment E1).
- **USB static-discharge protection, SOT-23-6** (main-33): Lifecycle: Active (DigiKey). DigiKey prices: 0.36 at 1, 0.243 at 10, 0.163 at 100, 0.114 at 1,000. USBLC6-2SC6Y is the automotive part, and another maker sells a copy under the same name: order the STMicroelectronics part. Newark's page carries its 'no longer stocked' flag. The same part is U1 on the cradle.
- **3.3 V regulator with enable for the USB supply pin, SOT-23-5** (main-34): Upgraded from PROVISIONAL in the review, as a listing on regional DigiKey pages that show the same DigiKey product; the US page came up in none of the four searches. DigiKey's title: 'Linear Voltage Regulator IC Positive Fixed 1 Output 250mA SOT-23-5'. The Denmark and Germany figures were written '44.232' and '108.067' and are read as thousands. Part status not seen. Prices seen only as aggregator copies (not counted): DigiKey 0.57 at 1, 0.469 at 1,000; Mouser 0.4409 at 1. Same family as U8. Read the live US page before ordering. Rev E: this is U11 on the BOM (E26 is in the netlist; design action A8); the DigiKey order code is still open, because A8 asks for the live US page first. The roll-up uses the aggregator figures and does not count them as seen.
- **Ideal-diode switch, SC-70-6** (main-35): Upgraded from PROVISIONAL in the review: the first search had found the part only at LCSC (China), which alone flags it 'not recommended for new designs'. DigiKey's title, 'OR Controller P-Channel 1:1 SC-70-6', confirms the package that E25 names. Lifecycle: Active at TI, DigiKey, Arrow and Findchips (as the reviewer reported). USD prices seen: 0.29 for one on cut tape and 0.132 at 500, on DigiKey pages priced in USD (the reviewer's record names the Mexico page for both; an earlier correction note gave the US page for the first). Basis: four searches on 2026-11-13 (two by the reviewer, two in the corrections); the figures are search-result summaries, not opened pages. Rev E: this is U12 on the BOM (E25 is in the netlist; design action A7), order code DigiKey 296-53541-1-ND.
- **32.768 kHz crystal, 3.2 x 1.5 mm** (main-36): Prices seen: DigiKey 0.94 to 0.99 at 1 and 0.55378 at 15,000; Newark about 1.07 at 1 falling to 0.706 at 5,000. The BOM says 0.68. ABS07-32.768KHZ-6-T and ABS07-LR-32.768KHZ-6-T are different order codes. The series resistance in the BOM description was not seen. DigiKey order code not seen.
- **Resistor 6.04 kohm 1 % 0402 (not fitted)** (main-37): DNP means 'do not populate': the pads exist, the part is left off. Lifecycle: active (Arrow). Newark lists 0.004 at 10,000. VERIFIED means the listing was seen.
- **Display (memory LCD, 1.28 inch, 128 x 128)**: Status reads: listed; stock and life-cycle not established. Lifecycle: DigiKey 'Part Status Active'; Octopart and Ciiva 'Production'; an old Mouser page and the reseller West Florida Components say obsolete; no Sharp notice and no named successor were found in two independent searches; Sharp's own page was not seen. DigiKey tray prices seen today: 12.39 at 1, 9.60 at 10, 7.97 at 100, 7.74 at 500 (it was 8.82 at 10 on 2026-11-11; which capture is the newer is not known). Future: 5.56 at 2,240 or more (another page 6.54). Standard package 1,120. Thickness is 0.741 mm in today's extracts against 0.746 mm in the design. LS013B7DH03-DU is a separate code that DigiKey marks no longer manufactured. Section 9.2; design action A11.
- **Lithium-polymer cell with protection board, 2 x 10 x 30 mm, 43 mAh**: Status reads: listing seen; availability and price PROVISIONAL until PowerStream answers. Listed at 12.00 each with the protection board and 10.00 without, at quantity 1; 'prices are subject to change, please inquire for current prices'. The protection board 'is optional, and only included when requested': order in writing as GM201030-PCB. Volume price columns had no readable quantities. 'UN38.3' is printed against the bare cell; the length with the board, the protection thresholds and other certificates were not seen. Three searches found no second US seller. Section 9.3; design action A12.

### 3.1 Alternates and replacement parts for the marker board

These 20 rows are not lines of the bill of materials. Sixteen are candidates beside a line that names only one maker; each
has its own status, and none is an approved alternate until the designers say so (design actions A4, A9, A14 and A18). Four
are history: the parts of revision D that revision E took off the board (the obsolete 1 uF and the discontinued 2.2 uF
capacitor numbers, the Schottky diode D17 and the MCP1700 at U11). Their replacements are lines 3, 6, 35 and 34 of the table
above. Do not buy a history row.

| For | Part number | Maker | US source | Stock or lead time as seen | Status | Remarks |
|---|---|---|---|---|---|---|
| Superseded at rev E, was the 1 uF line of rev D: capacitor 1 uF 10 V X5R 0402 (history: rev D part of main-03) | GRM155R61A105KE15D | Murata | [none to buy from: DigiKey lists it as obsolete; Arrow as last-time buy on one listing and obsolete on another; Mouser and Newark pages exist with no stock figure](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A105KE15D/965904) | No distributor stock figure seen; aggregator pages show residual lots only | **PROVISIONAL** 2026-11-13 | Not on the rev E BOM. Held at PROVISIONAL because the part cannot be bought as named. That it is obsolete was seen today and confirmed by a second, independent search. The number decodes correctly (0402, X5R, 10 V, 1 uF, 10 %); it is the part that has gone, not the value. Design action A1; loss of capacitance under working voltage: A3. |
| Second source for the 1 uF line: capacitor 1 uF 16 V X5R 0402 (alternate for main-03) | GRM155R61C105KA12D | Murata | [DigiKey (seen only as a 'listed substitute' on the page of another, obsolete part)](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61C105KE01D/5027538) | About 170,806 in stock, read from a substitute line on another part's page | **PROVISIONAL** 2026-11-13 | Downgraded by the second check: no listing for the exact number was seen, and the link is another part's page. Read its own DigiKey page and Murata's status before adopting it. |
| Superseded at rev E, was the 2.2 uF line of rev D: capacitor 2.2 uF 10 V X5R 0402 (history: rev D part of main-06) | GRM155R61A225KE95D | Murata | [none with stock: DigiKey says the product is no longer available there; Arrow lists it as 'LTB-Unconfirmed' (last-time buy)](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A225KE95D/5027536) | DigiKey: no longer available. Arrow: tape-and-reel listing, no stock figure seen. Octopart names Newark, no stock count in the extract | **PROVISIONAL** 2026-11-13 | Not on the rev E BOM. Held at PROVISIONAL because no US source was seen offering it. The number decodes correctly (0402, X5R, 10 V, 2.2 uF, 10 %). The 20 % sibling GRM155R61A225ME95D is obsolete at DigiKey, and DigiKey describes the large-reel code ...KE95J as not normally stocked. Design action A2; loss of capacitance under working voltage: A3. |
| Candidate for the 2.2 uF line: automotive-grade capacitor 2.2 uF 10 V X5R 0402 (alternate for main-06) | GRT155R61A225KE01D | Murata | [DigiKey (seen as a 'Parametric Equivalent' row, not on its own page)](https://www.digikey.com/en/products/detail/murata-electronics/GRT155R61A225KE01D/5416675) | A cross-reference row said 'In Stock: 92,425'; no price, status or date | **PROVISIONAL** 2026-11-13 | Downgraded by the second check: the 1 uF sister of this series showed 0 stock at Future and at Avnet (98-week lead), so stock in this series should not be assumed. Read its own page before naming it the stocked choice. |
| Second source for the 2.2 uF line: capacitor 2.2 uF 10 V X5R 0402 (alternate for main-06) | CL05A225KP5NSNC | Samsung Electro-Mechanics | [Mouser; DigiKey (1276-1108-1-ND, out of stock)](https://www.mouser.com/ProductDetail/Samsung-Electro-Mechanics/CL05A225KP5NSNC?qs=X6jEic/HinAxUPrdb0PbTA%3D%3D) | Mouser: 29,841 in stock, factory lead 15 weeks. DigiKey: out of stock, backorder | **VERIFIED** 2026-11-13 | No price seen. Lifecycle not seen. Not re-checked by the second pass. |
| Approved-alternate candidate for the 100 nF line: capacitor 100 nF 16 V X7R 0402 (alternate for main-01 and cradle-01) | CL05B104KO5NNNC | Samsung Electro-Mechanics | [Mouser; Newark; Future Electronics; DigiKey (1276-1001-1-ND)](https://www.mouser.com/en/ProductDetail/Samsung-Electro-Mechanics/CL05B104KO5NNNC/?qs=hqM3L16%2BxlfT2SKOuAUq6Q%3D%3D) | Mouser: about 4.55 million in stock, 4.08 million on order, factory lead 30 weeks. Newark: about 550,000. Future: about 46,248 on cut tape. DigiKey: CONFLICTING between two snapshots of the same order code on the same day (out of stock in one; 3,534,602 on a US-dollar page in the other) | **VERIFIED** 2026-11-13 | DigiKey USD prices on the page that showed stock: 0.08 at 1, 0.009 at 10, 0.0064 at 100. Newark: 0.003 at 10,000 or more. Read the live page before naming a distributor. Lifecycle not seen. Design action A4. |
| Second source for the 4.7 uF line: capacitor 4.7 uF 6.3 V X5R 0402 (alternate for main-02) | CL05A475MQ5NRNC | Samsung Electro-Mechanics | [DigiKey (1276-1056); Arrow; Newark; Future Electronics](https://www.digikey.com/en/products/detail/samsung-electro-mechanics/CL05A475MQ5NRNC/3889142) | DigiKey: 224,021 in stock on one listing, out of stock with a 61-week lead on the other. Arrow: 1,530,000. Newark: 10,000 and 30,000 on two listings. Future: 0 to 780,000 depending on the listing | **VERIFIED** 2026-11-13 | The sibling CL05A475MQ5NQNC is obsolete at DigiKey: order the exact suffix. No price seen. |
| Second source for the 10 nF line: capacitor 10 nF 50 V X7R 0402 (alternate for main-04) | CL05B103KB5NNNC | Samsung Electro-Mechanics | [DigiKey; Avnet; Mouser; Newark](https://www.mouser.com/ProductDetail/Samsung-Electro-Mechanics/CL05B103KB5NNNC?qs=349EhDEZ59pcaIbMQHo3bQ%3D%3D) | DigiKey: about 4.3 million (a purchase limit applies). Avnet: about 1.44 million, factory lead 20 weeks. Mouser: about 590,173. Newark: 316 | **VERIFIED** 2026-11-13 | No price seen. |
| Second source for the 6.8 pF line: capacitor 6.8 pF 50 V NP0 0402 (alternate for main-05) | CC0402CRNPO9BN6R8 | Yageo | [DigiKey; Future Electronics](https://www.digikey.com/en/products/detail/yageo/CC0402CRNPO9BN6R8/2345080) | DigiKey: active, about 238,497 in stock (a filter page showed 160,421). Future: 320,000 shown; the figure looks stale | **VERIFIED** 2026-11-13 | Same +-0.25 pF tolerance. Only the 10,000-piece price was seen (about 0.0044). |
| Third source for the 6.8 pF line: capacitor 6.8 pF 50 V C0G 0402 (alternate for main-05) | C0402C689C5GACTU | KEMET | [DigiKey; Newark](https://www.digikey.com/en/products/detail/kemet/C0402C689C5GACTU/2196920) | DigiKey: about 132,025 in stock, standard lead 17 weeks. Newark: 9,604 | **VERIFIED** 2026-11-13 | Same +-0.25 pF tolerance. No price seen. |
| Second source for the 10 pF line: capacitor 10 pF 50 V C0G 0402 (alternate for main-07) | CL05C100JB5NNNC | Samsung Electro-Mechanics | [DigiKey; Newark](https://www.digikey.com/en/products/detail/samsung-electro-mechanics/CL05C100JB5NNNC/3886797) | DigiKey: 490,160 in stock, Active (a purchase limit applies) | **VERIFIED** 2026-11-13 | Newark prices: 0.100 at 1, 0.028 at 25, 0.016 at 100, 0.011 at 500. |
| Second source for the 10 kohm line: resistor 10 kohm 1 % 0402 (alternate for main-14) | ERJ-2RKF1002X | Panasonic | [DigiKey; Newark; Future Electronics](https://www.digikey.com/en/products/detail/panasonic-industry/ERJ-2RKF1002X/192073) | DigiKey: 2,259,980 in stock, standard lead 15 weeks. Newark: 207,234. Future: 3,598,000 shown, though its USA and global figures read 0 on the same page | **VERIFIED** 2026-11-13 | Future: 0.0045 at 10,000 or more. |
| Second source for the 100 kohm line: resistor 100 kohm 1 % 0402 (alternate for main-15) | ERJ-2RKF1003X | Panasonic | [DigiKey; Newark](https://www.digikey.com/en/products/detail/panasonic-electronic-components/ERJ-2RKF1003X/192081) | DigiKey: 3,664,998 in stock. Newark: 1,730,000 and 127,286 on two listings | **VERIFIED** 2026-11-13 | No price seen. |
| Second sources for the other ten resistor values: 0402 1 % (alternates for main-13, main-16 to main-23 and main-37) | ERJ-2RKF10R0X, ERJ-2RKF1001X, ERJ-2RKF2201X, ERJ-2RKF33R0X, ERJ-2RKF6811X, ERJ-2RKF1004X, ERJ-2RKF68R0X, ERJ-2RKF4703X, ERJ-2RKF1503X, ERJ-2RKF6041X | Panasonic | not checked (the same series as the two verified values) | not checked | **PROVISIONAL** 2026-11-13 | Part numbers built from Panasonic's value coding, from memory. Only a Mouser page title for ERJ-2RKF10R0X was seen; ERJ-2RKF68R0X was searched and no listing surfaced; the other eight were not searched (search cap). Confirm each number before it goes on an approved-alternates list. |
| Second source for the resistor arrays: 4 x 220 ohm, 0804 (alternate for main-24) | YC124-JR-07220RL | Yageo | [DigiKey (YC124J-220CT-ND)](https://www.digikey.com/en/products/detail/yageo/YC124-JR-07220RL/1005537) | DigiKey: 6,683 in stock (a later snapshot 5,185), active, standard lead 18 weeks | **VERIFIED** 2026-11-13 | Compare its land pattern and height with the Panasonic part before approving it. No price seen. Not re-checked by the second pass. |
| Second source for the temperature sensors: NTC thermistor 10 kohm 1 %, 0402 (alternate for main-25) | NTCG103JF103FT1 | TDK | [DigiKey; Newark; Mouser (0 in stock); Future Electronics (0 in the USA)](https://www.newark.com/tdk/ntcg103jf103ft1/ntc-thermistor-10k-0402/dp/81AH9122) | DigiKey: about 395,079 in stock. Newark: 43,837. Mouser: 0, with 103,629 on order. Future: 0 in the USA, 10,000 on order | **VERIFIED** 2026-11-13 | DigiKey: 0.11 for one. Its B value is quoted as 3435 K by DigiKey, Newark and Mouser and as 3380 K by Future (probably the 25/85 and 25/50 figures of one part). Sourcing is confirmed, equivalence is not: compare the TDK and Murata resistance-temperature tables at the charger's and the firmware's thresholds first. Not re-checked by the second pass. |
| Alternative named in the design for the infrared LEDs: 850 nm LED, 0402 (alternate for main-09) | IN-S42CTQIR | Inolux | [DigiKey (product 10384804). Arrow has a catalogue page with no stock or price. No Mouser or Newark listing](https://www.digikey.com/en/products/detail/inolux/IN-S42CTQIR/10384804) | DigiKey US page: 570 in stock, manufacturer lead 8 weeks. Regional DigiKey pages: 1,991 (Canada, Switzerland), 15,389 (Finland), 18,101 (Korea, India) | **VERIFIED** 2026-11-13 | DigiKey US prices: 0.26 at 1, 0.174 at 10, 0.1219 at 100, 0.09006 at 1,000, 0.064 at 40,000 on reel. 850 nm, 1.6 V, 70 mA, 140 degrees; 5.5 mW/sr typical at 70 mA against 9 for the SFH 4053B. Pad layout not checked. Lifecycle not seen. Design action A9. |
| Tape-and-reel code of the flash memory (alternate packaging for main-29) | MX25R6435FZNIL0 TR | Macronix | [Arrow (US page); Mouser (written there as MX25R6435FZNIL0-TR)](https://www.arrow.com/en/products/mx25r6435fznil0tr/macronix-international) | Arrow US: 4,000 parts, ships in 2 days. Mouser: 84 can ship immediately in one snapshot (its 'expected' date is already past, so the snapshot is old); 10,116 in another | **VERIFIED** 2026-11-13 | Prices seen: Arrow 1.6608; Mouser cut tape 3.61 at 1 in one snapshot, 1.67 in the other. Design action A14. |
| Retired at rev E by amendment E25, was D17 of rev D: Schottky diode 30 V 0.5 A, SOD-323 (history: rev D BOM line 10 (D17); no reference on the rev E board) | B0530WS-7-F | Diodes Incorporated | [DigiKey (B0530WS-FDICT-ND); Newark (12T1452)](https://www.digikey.com/en/products/detail/diodes-incorporated/B0530WS-7-F/816523) | Conflicting: one DigiKey listing 403 in stock; the listing under B0530WS-FDICT-ND 'out of stock, can be backordered'; DigiKey UK page 35,014; an aggregator copy 108,417. Lead time not seen today (40 weeks on 2026-11-11) | **VERIFIED** 2026-11-13 | Prices seen: DigiKey 0.34 at 1, 0.1307 at 100, 0.07114 at 3,000 on reel; Newark 0.504 at 1, 0.118 at 1,000. The BOM says 0.30. Not on the rev E BOM: do not buy it. Design action A7. |
| Retired at rev E by amendment E26, was U11 of rev D: 3.3 V regulator for the USB supply pin, SOT-23 (history: rev D part of U11 (rev D BOM line 35)) | MCP1700T-3302E/TT | Microchip | [DigiKey (product 652676); Mouser; Newark](https://www.digikey.com/en/products/detail/microchip-technology/MCP1700T-3302E-TT/652676) | DigiKey 10,078 in stock; Mouser 195,299; Newark 14,015 (a separate Newark full-reel listing is out of stock) | **VERIFIED** 2026-11-13 | Prices seen: 0.51 at 1 (DigiKey, Mouser, Newark), 0.43 at 25 (DigiKey). MCP1700T-3302E/TTVAO is a different (automotive) code. DigiKey order code not seen. Lifecycle not seen. Not on the rev E BOM. Design action A8. |

Not found, and therefore not in the table: Samsung CL05C6R8CB5NNNC (a second source for the 6.8 pF line), searched once by its
exact number on seven US distributor sites; its +-0.1 pF sibling CL05C6R8BB5NNNC is obsolete at DigiKey.

---

## 4. Electronic parts on the charging cradle

The cradle now has its own netlist and bill of materials (`electrical/gl1_cradle/netlist_out/gl1_cradle-bom-status.csv`, 7
lines). The consumer cradle carries four spring pins; the factory fixture carries three more, which is why the last line is
marked "not fitted". The two design changes that revision 3 asked for are in the revision E board: the fuse (A5; line 2 is
now the Littelfuse part) and the spring pins' holes (A6). The board is 1.0 mm thick since amendment E36.

| BOM line | Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|---|
| cradle-01: C1 | Capacitor 100 nF 16 V X7R 0402 (1 per cradle) | GRM155R71C104KA88D | Decoupling capacitor: a small reservoir of charge on the 5 V line beside the static-protection chip | [DigiKey (490-3261-1-ND cut tape, 490-3261-2-ND reel); Future Electronics; Arrow](https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88D/1644733) | not seen / 0.00805 | Conflicting: a DigiKey Mexico punch-out page says 0 in stock, backorder, 12-week lead; aggregator copies of DigiKey say 12,925,621 and 3,438,352; another DigiKey page 4,948,426. Future: about 220,000 (global) | medium: same part and same conflicting life-cycle flag as main-01 | Samsung CL05B104KO5NNNC: VERIFIED, own row | **VERIFIED** 2026-11-13 |
| cradle-02: F1 | Resettable fuse on the 5 V line, 0603 (1 per cradle) | 0603L035YR | Limits the current if metal bridges the charging pads (a hard short), and resets by itself afterwards; 1 ohm at most after a trip (E25) | [DigiKey (two product entries, 1920186 and 1920207; cut tape F2903CT-ND per one extract); Mouser (576-0603L035YR), Arrow, TTI and Newark through aggregator copies](https://www.digikey.com/en/products/detail/littelfuse-inc/0603L035YR/1920186) | not seen / not seen | DigiKey US page: 17,643 in stock (an undated copy), manufacturer lead 10 weeks; one regional DigiKey page: out of stock, backorder. Aggregator copies: Mouser 3,743, Arrow 27,510 | low for supply. Two things to accept: it trips at 0.75 A, not 0.5 A, and its 6 V rating has no margin over a 5.5 V bus | Bourns MF-FSMF035X-2 (VERIFIED, own row). With voltage margin but a larger footprint: Bourns MF-NSMF050-2 (own row) | **VERIFIED** 2026-11-13 |
| cradle-03: J1 | USB-C socket (1 per cradle) | USB4105-GF-A | Where the charging cable plugs into the cradle | [DigiKey (2073-USB4105-GF-ACT-ND); Mouser (640-USB4105-GF-A); Future Electronics (listing link)](https://www.findchips.com/search/USB4105-GF-A) | not seen / not seen | Aggregator copy: DigiKey 55,854 in stock with a 9-week lead. A DigiKey Australia page extract: about 129,614. A DigiKey Germany punch-out page: out of stock, backorder | low: one maker, several distributors, deep stock. Another maker's socket would need its own land pattern | Same part at Mouser and Future. Do not substitute USB4105-GF-A-060, which appeared in the same results, without reading what the suffix changes | **VERIFIED** 2026-11-13 |
| cradle-04: R1 R2 | Resistor 5.1 kohm 1 % 0402 (2 per cradle) | RC0402FR-075K1L | Tell a USB-C charger to switch its 5 V on | [DigiKey (311-5.10KLRCT-ND; regional pages)](https://www.digikey.com.au/en/products/detail/yageo/RC0402FR-075K1L/726624) | not seen / not seen | Conflicting between DigiKey's two product entries: entry 726624 (Australia page) 525,003 in stock; entry 729571 (Switzerland, Hong Kong and UK pages) 0 or backorder; standard lead 18 weeks on one page | low | Any 5.1 kohm 1 % 0402 thick-film resistor fits. Panasonic ERJ-2RKF5101X, Vishay CRCW04025K10FKED (from memory, not searched: PROVISIONAL) | **VERIFIED** 2026-11-13 |
| cradle-05: SP1 SP2 SP3 SP4 | Spring pins (4 fitted in the consumer cradle) | 0914-0-15-20-77-14-11-0 | Touch the marker's gold pads to charge it and talk to it | [DigiKey (ED8185-ND; regional pages); Future Electronics (listing link, stock not read)](https://www.digikey.at/product-detail/en/mill-max-manufacturing-corp/0914-0-15-20-77-14-11-0/ED8185-ND/1147053) | not seen / not seen | DigiKey UK page: 68,871 in stock; DigiKey Austria page: 60,336; manufacturer lead 4 weeks. The US page's stock was not in an extract | medium: supply looks easy (stock was seen on two regional DigiKey pages; the US page's figure was not), but it is a single-maker part and its tail length is an estimate (the footprint was corrected at rev E: 0.635 mm tail in a 0.80 mm finished hole) | Long-tail version of the same pin, 0914-1-15-20-77-14-11-0 (PROVISIONAL, own row). No other maker | **VERIFIED** 2026-11-13 |
| cradle-06: U1 | USB static-discharge protection, SOT-23-6 (1 per cradle) | USBLC6-2SC6 | Protects the USB lines from static shocks | [DigiKey (497-5235-1-ND); Arrow; Newark](https://www.digikey.com/en/products/detail/stmicroelectronics/USBLC6-2SC6/1121688) | 0.243 / 0.114 | DigiKey about 113,703 in stock (aggregator copies of the same DigiKey number: 156,665 with a 25-week lead, and 67,477); Arrow 18,492; Newark about 138,000 | low | Same part at Arrow and Newark | **VERIFIED** 2026-11-13 |
| cradle-07: SP5 SP6 SP7 (DNP) | Spring pins (3 more, fitted only in the factory fixture) | 0914-0-15-20-77-14-11-0 | The three extra contacts (programming and reset) that only the factory's cradle needs | [DigiKey (ED8185-ND; regional pages); Future Electronics (listing link, stock not read)](https://www.digikey.at/product-detail/en/mill-max-manufacturing-corp/0914-0-15-20-77-14-11-0/ED8185-ND/1147053) | not seen / not seen | As cradle-05: DigiKey UK page 68,871 in stock; Austria page 60,336; manufacturer lead 4 weeks | medium: as cradle-05 | As cradle-05 | **VERIFIED** 2026-11-13 |

Country of manufacture: not found for any line in this table.

Notes on these lines:

- **Capacitor 100 nF 16 V X7R 0402 (1 per cradle)** (cradle-01): Lifecycle: conflicting (not recommended for new designs at Octopart, IBS and LCSC; Active at Arrow and Future). DigiKey prices: 0.10 at 1, 0.00805 at 1,000, 0.00684 at 5,000. Same part as main-01. Design action A4.
- **Resettable fuse on the 5 V line, 0603 (1 per cradle)** (cradle-02): DigiKey: 6 V, hold 350 mA, trip 750 mA, 40 A maximum, Active. Resistance after a trip 1 ohm maximum (from distributor data, 0.200 to 1.000 ohm on one source; the maker's own table was not in an extract); initial resistance 200 milliohm minimum. At 30 mA the drop is 0.03 V at most. Prices came from an aggregator page whose search string was for a slightly different number, so they are not counted as seen: 0.839 at 10 (Newark), 0.395 at 4,000 (Arrow). Rev E: this is F1 on the cradle BOM (design action A5 applied in electrical/gl1_cradle). Its 0.75 A trip current against amendment E6's 'about 0.5 A' is a recorded departure for the specification owner. The roll-up uses the aggregator figures and does not count them as seen.
- **USB-C socket (1 per cradle)** (cradle-03): Evidence grade: aggregator copy plus regional DigiKey pages, and the web address on this row is the aggregator's, not a distributor's product page (a DigiKey Singapore page was seen on 2026-11-11, with 0.917 at 10). Prices seen today: DigiKey 0.365 at 20,000; Mouser about 0.44 at 2,400 (aggregator copy). The BOM says 1.09. Not re-checked by the second pass. The project's land pattern is a modified copy and has not been checked against GCT's drawing.
- **Resistor 5.1 kohm 1 % 0402 (2 per cradle)** (cradle-04): Regional DigiKey pages with the same DigiKey number; the US page was not seen. No USD price seen (about EUR 0.08 at 1). The two product entries are probably the two packagings (the researcher's reading, not in an extract). Replaces the '5.1 kohm class' row of rev 2. The BOM's Distributor PN cell can be filled: 311-5.10KLRCT-ND.
- **Spring pins (4 fitted in the consumer cradle)** (cradle-05): Confirmed from DigiKey: working heights 6.96 / 5.82 / 4.67 mm (maximum / recommended / minimum). element14: overall length 8.3 mm; 25 g initial and 60 g at working travel. Mill-Max data, as summarised by the search: tail diameter 0.025 in (0.635 mm) in a 0.029 in (0.737 mm) minimum mounting hole; the rev D netlist assumed a 0.76 mm tail in a 0.90 mm hole; the rev E board has a 0.80 mm finished hole for the 0.635 mm tail (A6). Tail length is not confirmed: 8.3 mm overall less 6.96 mm above the board gives about 1.34 mm (a subtraction, not a reading), which was shorter than the 1.6 mm board of rev D; the rev E board is 1.0 mm (amendment E36), so about 0.34 mm of tail would come through. Barrel and plunger diameters were not seen. Prices on 2026-11-11: 0.85 at 1 (DigiKey), 0.88 at 1,000 (Future); none seen today. The Mill-Max drawing could not be opened from this session. Design action A6.
- **USB static-discharge protection, SOT-23-6 (1 per cradle)** (cradle-06): Lifecycle: Active (DigiKey). Same part as main-33 (U10); the distributor-page evidence is the main-board row's. DigiKey prices: 0.36 at 1, 0.243 at 10, 0.114 at 1,000.
- **Spring pins (3 more, fitted only in the factory fixture)** (cradle-07): Same part as cradle-05; DNP ('do not populate') in the consumer cradle. The footprint finding of cradle-05 applies to all seven positions. Design action A6.

### 4.1 Replacement and candidate parts for the cradle board

| For | Part number | Maker | US source | Stock or lead time as seen | Status | Remarks |
|---|---|---|---|---|---|---|
| Superseded at rev E, was the cradle fuse of rev D: resettable fuse 0603, hold 0.2 A, trip 0.5 A, 9 V (history: rev D part of cradle-02 (F1)) | MF-FSMF020X-2 | Bourns | [DigiKey (regional pages of DigiKey product 2039254); Avnet Americas (listing link, not read)](https://www.digikey.co.za/en/products/detail/bourns-inc/MF-FSMF020X-2/2039254) | Conflicting: DigiKey South Africa page 55,272 in stock with a 14-week lead; DigiKey Spain page 22,319; DigiKey Canada punch-out page: out of stock, backorder. US page not seen | **VERIFIED** 2026-11-13 | Not on the rev E BOM. VERIFIED as a listing; it did not match the design as amended. DigiKey: 9 V, hold 200 mA, trip 500 mA, time to trip 600 ms, initial resistance 550 milliohm minimum, post-trip resistance 3.5 ohm maximum. At the marker's 30 mA it can drop up to 0.105 V, which is the loss E25 set out to remove. No price seen. Replaces the 'not specified' fuse row of rev 2 (amendment E6). Design action A5. |
| Second source for the cradle fuse: resettable fuse 0603, hold 0.35 A, trip 0.75 A, 6 V (second source for cradle-02 (F1)) | MF-FSMF035X-2 | Bourns | [Master Electronics; Online Components; DigiKey (MF-FSMF035X-2CT-ND; regional pages); Avnet Americas (listing link)](https://www.masterelectronics.com/en/bourns/mffsmf035x2-10751533.html) | Master Electronics: 24,430 in stock, minimum order 1,000. Online Components: 18,000, minimum 1,500. DigiKey regional pages (product 2039255): about 41,000 to 43,000, 19-week lead; an Austria punch-out page: out of stock | **VERIFIED** 2026-11-13 | DigiKey: 6 V, hold 350 mA, trip 750 mA, time to trip 100 ms, post-trip resistance 1.4 ohm maximum. RS lists 0.2 ohm minimum and 1.4 ohm maximum without calling it the post-trip figure. Online Components: 0.1718 at 1,500. That Master Electronics and Online Components ship from the US is from memory. |
| Fallback for the cradle fuse with voltage margin: resettable fuse 1206, hold 0.5 A, trip 1 A, 13.2 V (fallback for cradle-02 (F1); needs a 1206 footprint) | MF-NSMF050-2 | Bourns | [DigiKey (a series highlight page and regional pages)](https://www.digikey.com/en/product-highlight/b/bourns/multifuse-polymer-ptc-resettable-fuses-mf-nsmf-series) | Series page: DigiKey US highlight page '76467 - Immediate'. DigiKey Spain page: 85,450. DigiKey Canada punch-out page: out of stock. 16-week lead on the South Africa page | **VERIFIED** 2026-11-13 | Evidence grade: series highlight page, not the part's own listing. DigiKey: 13.2 V, hold 500 mA, trip 1 A, time to trip 100 ms, post-trip resistance 700 milliohm maximum. A price of 0.38 was seen at an unstated quantity. Hold 0.5 A is the top of E25's range. |
| Candidate for the spring pins: the same pin with a longer solder tail (candidate for cradle-05 and cradle-07) | 0914-1-15-20-77-14-11-0 | Mill-Max | [DigiKey (product 5361065; listing links only)](https://www.digikey.co.uk/en/products/detail/mill-max-manufacturing-corp/0914-1-15-20-77-14-11-0/5361065) | not seen | **PROVISIONAL** 2026-11-13 | element14's title gives 11.35 mm overall, 3.05 mm longer than the standard pin. Stroke, working height and tail diameter were not read. A longer tail stands out below the board: check the room under it. Design action A6. |

The 100 nF alternate (Samsung CL05B104KO5NNNC) serves the cradle's C1 as well; it is in the table of section 3.1.

---

## 5. Mechanical purchased parts

These parts are not on a board's BOM, so the tables from here on have no BOM-line column. The two prism lines and the EVT
cover glass were not checked again and keep their 2026-11-11 date.

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Fold prism, 2.0 mm (2 per marker) | 32-526 | Tiny mirror-prisms that turn each camera's view from 'up' to 'forward' | [Edmund Optics (Barrington, New Jersey), direct](https://www.edmundoptics.com/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392/) | 94.50 / quote | '20+ in stock' at the snapshot | medium: easy to buy today, but the largest cost in a small build (about 189 USD per marker at 10 units) | Knight Optical PTK0202 (2 x 2 mm, protected coating, USD 56.02). A UK maker; a review reports a US sales company, Knight Optical (USA) LLC in North Kingstown, Rhode Island (not re-checked). Ask whether PTK0202 ships from US stock and what its size tolerance is | **VERIFIED** 2026-11-11 |
| Fold prism, production volume source | custom: 2.0 mm right-angle, N-BK7, aluminised hypotenuse | Same prism, bought in thousands | [Precision Micro-Optics (catalogue micro prisms); Tower Optical and Edmund Optics by quote](https://pmoptics.com/Right_Angle_Prisms.html) | quote / quote | not found | high until quoted: no published volume price for a 2.0 mm aluminised prism was found | Edmund 32-526 at its 26 to 49 price (78.50) | **PROVISIONAL** 2026-11-11 |
| Ball feet, 1.0 mm (3 per marker) | Boca Bearings '1MM-C SI3N4 BALL GRADE 5 (1 PC)' (silicon nitride; PROPOSED here for EVT: the design allows 316 stainless or silicon nitride) | The three hard feet the marker stands on | [Boca Bearings (Florida; the state is from memory)](https://www.bocabearings.com/products/bearingballtypes/balls/ceramic-silicon-nitride-si3n4-series?ProductType=0) | not seen / not seen | stock not seen: the page shows no count | medium: easy to buy singly, but about USD 7 of balls per marker with no volume price seen, and no US listing with a grade, a price or stock was found for the 316 stainless alternative | 316 stainless, grade 100, 1.0 mm: no current US listing with a part number, price or stock (Salem Specialty Ball's inventory page is about 1,950 days old; Thermo Scientific catalogue number 042018 is 1 mm type 316 spheres with no grade stated; McMaster's 316 line showed no size under 2.5 mm in two searches): PROVISIONAL, by request for quote. Other silicon nitride sellers: VXB (PROVISIONAL: its text says '1mm (3/64 inch)', and 3/64 inch is 1.19 mm, too big for the 1.10 mm holes) and Precision Plastic Ball (PROVISIONAL: a page title only, by quotation) | **VERIFIED** 2026-11-13 |
| Cover glass, EVT (flat mineral-glass watch crystal, 28.0 x 1.0 mm) | Esslinger 'flat round standard mineral glass crystal, 1 mm thick', size 28.0 | Clear window over the display | [Esslinger (St. Paul, Minnesota)](https://www.esslinger.com/watch-crystal-flat-round-standard-mineral-glass-crystal-1mm-thick/) | 1.65 / n/a | stock not seen: sold singly in 0.1 mm size steps from 12 to 40 mm; stock not shown | low for EVT (but this glass is not step-proof) | Jules Borel sapphire crystal 28.0 x 1 mm (seen again 2026-11-13: 11.00 at 1 to 2, 10.45 at 3 to 9, 9.90 at 10 or more; item code probably SR10 280; tolerances not stated). Caution: sapphire is birefringent and sits above a polarised display; docs/research/display.md finding 6 advises against it, and the E9 sunglasses trial would have to be repeated with it | **VERIFIED** 2026-11-11 |
| Cover glass, production (chemically strengthened, printed black border) | custom: dia 28.0 x 1.0 mm aluminosilicate, ring-on-ring strength 600 MPa or more | Stronger window over the display (the step test is still to be passed) | [Abrisa Technologies (Santa Paula, California) and Valley Design Corp., both by quote](https://valleydesign.com/gorilla-glass/) | quote / quote | custom; no lead time or price seen | medium to high: 1.0 mm is not a stocked thickness of chemically strengthened glass at either fabricator seen, so the design as drawn cannot be bought without a change | Sapphire watch crystal 28.0 x 1.0 mm from Jules Borel (11.00 falling to 9.90 at 10 or more): only if the E9 trial is repeated with sapphire, which is birefringent | **PROVISIONAL** 2026-11-13 |
| Visor windows, 0.40 mm borosilicate, cut 5.0 x 3.25 mm (2 per marker) | custom, SCHOTT D 263 T eco, 0.4 mm, diced | Small flat windows that keep water out of the two camera openings | [Valley Design Corp. and Abrisa Technologies (Santa Paula, California), both by quote](https://www.photonicsonline.com/doc/precision-xy-saw-cutting-of-glass-wafers-and-filters-0001) | quote / quote | custom; no price or lead time seen | medium: a very small custom part, quote only | Edmund Optics stock 0.4 mm D 263 T eco windows, 25 x 25 mm, diced to size (rev 2; not re-checked) | **PROVISIONAL** 2026-11-13 |
| Pressure-equalisation vent, adhesive, 5.0 mm | VE80205 | A breathable patch: lets air move so the seals are not stressed, and keeps water out | [no US listing found. US channels named, both by enquiry: Sealing Devices Inc. (Lancaster, New York; named by Gore as an authorized distributor) and H-O Products](https://h-oproducts.com/product/gore-protective-vents-adhesive-series-ve8-ve7-and-ve9/) | not seen / not seen | US: not seen. Outside the US: RS sells packs of 50 (stock no. 287-9532) | medium to high: one maker, no stocked US seller found on two search days, and the water-entry pressure the design relies on (50 kPa) has not been seen for this part | Porex Virtek adhesive vent disc through Interstate Specialty Products (by enquiry: PROVISIONAL). Its PMV10 membrane is 175 mbar minimum, 270 typical (17.5 / 27 kPa), below the design's 50 kPa; of the other grades only PMV27 (1,050 mbar typical) clears 50 kPa with margin; and Porex's stock adhesive discs seen start at 7.0 x 3.0 mm, with no 5.0 x 2.0 mm size. A search of DigiKey, Mouser, Newark and Arrow found no adhesive vent of any brand. Donaldson: not found | **PROVISIONAL** 2026-11-13 |
| Rubber feet for the cradle (4 per cradle) | 3M Bumpon SJ5302 (PROPOSED here; the US-page listing seen is coded SJ5302-R25) | Stop the cradle sliding | [DigiKey (listings SJ5302 and SJ5302-R25; pack of 80: 3M156269-ND)](https://www.digikey.com/en/products/detail/3m/SJ5302-R25/7402682) | not seen / not seen | DigiKey US page, listing SJ5302-R25: 5,472 in stock. The plain SJ5302 listing: 64,528 on the UK page and 104,336 on the Australia page. Pack of 80: 41 in stock, 4-week lead (undated aggregator copy) | low for supply. Design item: it is 7.92 x 2.16 mm, not the 'dia 8 x 3' of the mechanical parts list | A McMaster-Carr adhesive-back bumper of 5/16 in x 7/64 in (about 7.9 x 2.8 mm) was seen once with its catalogue number cut short ('95495K2') and could not be found again: PROVISIONAL | **VERIFIED** 2026-11-13 |
| Screws for the cradle board, M2 x 4 thread-forming for plastic (4 per cradle) | not selected: a 4 mm screw of McMaster-Carr's 96817A family (96817A204 may be it: its length was not seen). 96817A207, the rev D candidate, is the 5 mm length | Hold the cradle's circuit board | [McMaster-Carr](https://www.mcmaster.com/pt-style-screws) | not seen / not seen | not seen; sold in packs of 25 | medium: no part number for a 4 mm screw has been seen. The catalogue number seen (96817A207) is 5 mm long, its thread size is not confirmed, and it is no longer the screw the model calls for (E36: M2 x 4) | McMaster 96817A204 may be the shorter length of the same family (its length was not seen); 96817A207 is the 5 mm and 96817A209 the 6 mm length. McMaster 90380A325 (Phillips; seen only in a third-party cross-reference) and Newport Fasteners 763450-1000 at Zoro (box of 1,000; link only): PROVISIONAL. DigiKey: not checked | **PROVISIONAL** 2026-11-13 |

Country of manufacture: not found for the lines above, except: Pressure-equalisation vent, adhesive, 5.0 mm: Germany (RS listing, rev 2).

Notes on these lines:

- **Fold prism, 2.0 mm (2 per marker)**: 105.00 at 1 to 5, 94.50 at 6 to 25, 78.50 at 26 to 49 (US page, bom-verification-opto.md). N-BK7, aluminised hypotenuse, dimensional tolerance +/-0.1 mm.
- **Fold prism, production volume source**: Tower Optical: only general prism capability and quote-only pricing were found, no 2.0 mm aluminised catalogue part. Precision Micro-Optics lists micro prisms with an aluminium hypotenuse at about USD 32 to 38 in 1.25 and 1.5 mm sizes; 2.0 mm not confirmed. This is the largest single uncertainty in the 1000-unit figure.
- **Ball feet, 1.0 mm (3 per marker)**: Replaces the McMaster 1598K16 row of rev 2: that ball is 440C stainless, which amendment E8 forbids. Price seen: 2.37 for one ball; no quantity break was seen. The second check could not re-see the price; it found the same item on an aggregator, spelled '1MM-C SI3N4 GR.5 BALLS-EA', where sister sizes fall only about 5 % at 2,500. Grade 5 means about +/-0.001 mm on diameter (two secondary tables). For E20: grade 100 = +/-0.0127 mm is confirmed at three ball makers (Thomson, Hartford Technologies, US Ball); grade 25 = +/-0.0025 mm at one (Acraball). Silicon nitride does not rust and is not magnetic; check that the potting epoxy bonds to it. Design action A19.
- **Cover glass, EVT (flat mineral-glass watch crystal, 28.0 x 1.0 mm)**: Listed at 1.50 on one page and 1.65 on another; 5 % off at 10 to 49, 10 % at 50 to 99, 15 % at 100+ (1.65 less 5 % is about 1.57). Diameter and thickness tolerance are not stated: measure on receipt (the recess is 28.5).
- **Cover glass, production (chemically strengthened, printed black border)**: Stocked thicknesses seen. Abrisa: Gorilla Glass 0.4, 0.55, 0.8, 1.1 and 2.0 mm; Dragontrail 0.8 and 1.1 mm; Xensation 0.55 to 2 mm (pages undated or from about 2020). Valley Design: Gorilla Glass 0.55, 0.7, 1.1, 1.3 and 2.0 mm, parts 'as small as 0.127 mm square'. Edmund Optics sells stock Gorilla Glass windows 1.10 +/-0.05 mm thick, a US shelf source of 1.1 mm sheet for trials. With 1.1 mm the glass sits 0.02 mm below flush in the 1.25 mm recess instead of 0.12 mm; with 0.8 or 0.7 mm the recess or the tape must change. One result states that strengthened sheet cannot be cut without cracking, so the disc must be cut and edged before it is strengthened. The 600 MPa figure, the 28.0 mm size and any price are unconfirmed. Swift Glass: not found. Design action A28.
- **Visor windows, 0.40 mm borosilicate, cut 5.0 x 3.25 mm (2 per marker)**: Valley Design says it dices D 263 and, on another page, that it can make parts 'as small as 0.127 mm square'; confirm that both statements apply to 0.4 mm D 263. Abrisa describes camera-assisted saw cutting of D 263 T eco from 0.2 mm thick with dimensional tolerances 'such as 0.025 mm' and edges 'well suited for epoxy bonding'; no minimum part size was seen. Abrisa also stocks the sheet and can coat it before cutting. SCHOTT's own cut-to-size service has minimum sizes of 10 to 20 mm. The recess gives 0.25 mm per side. Design action A29.
- **Pressure-equalisation vent, adhesive, 5.0 mm**: H-O Products lists the Gore adhesive series in seven sizes from 2.0 x 5.0 mm; neither US channel showed VE80205 with a price or stock. RS UK: GBP 2.933 each at 50 and GBP 1.578 at 1,000 (indicative). 2.0 mm vent area, 5.0 mm outside, 0.26 mm thick, 104 ml/min at 70 mbar. Gore says the IP rating depends on housing design and part size. The checker's arithmetic for a 2.0 mm opening at 70 mbar: Porex PMV10L about 44 ml/min, PMV20 about 13, PMV27 about 3.7, against 104 for the Gore part. Design action A22.
- **Rubber feet for the cradle (4 per cradle)**: DigiKey: 'Bumper Cylindrical, Dome 0.312 in Dia (7.92mm) Polyurethane Clear', thickness 0.085 in (2.16 mm). Price seen: 0.11146 each at 144 on the US page (the SJ5302-R25 listing; what '-R25' denotes was not read). The cradle's foot pockets are dia 8.4 x 1.0 deep, so this bumper drops in with 0.24 mm of play per side and stands 1.16 mm proud where a 3 mm bumper would stand 2.0 mm. No 3M bumper of dia 8 x 3 was seen. Not re-checked by the second pass. Design action A21.
- **Screws for the cradle board, M2 x 4 thread-forming for plastic (4 per cradle)**: Rev E (amendment E36: cradle board 1.0 mm): the mechanical model calls for M2 x 4 (mechanical/README.md part list item 24): 4 mm of screw less the 1.0 mm board leaves 3.0 mm of thread in pilot holes drilled dia 1.6 x 3.2 deep. No 4 mm part was searched: this revision made no search. Seen on 2026-11-13 for the 5 mm part 96817A207 only: head dia 3.35 mm, head height 1.6 mm, Torx Plus IP6 / T6, drill No. 52 (1.61 mm), pack of 25. 'M2' comes from a third-party cross-reference; one search summary read the heading above the row as 'M2.5'; the drill size suits M2. A 5 mm screw does not fit: it would ask for 4.0 mm of thread in a 3.2 mm hole. The 3.35 mm head is inside the 4.0 mm keep-out, if the 4 mm screw has the same head (not seen). Held at PROVISIONAL until a 4 mm part number, its size and its price are read on mcmaster.com. Design action A20.

---

## 6. Tapes, film and foam

A **converter** is a company that buys tape in wide rolls and cuts it into shaped parts. The tape maker (3M, tesa) does not
sell cut shapes itself. The cutting service is in section 8; this table is the material. A **transfer tape** is a film of
glue with no carrier inside it; a **double-coated tape** has a thin plastic carrier with glue on both faces.

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Adhesive sheet material, circuit board to base plate (FR-4 build) | 3M 93020LE | Double-sided tape that bonds the board to the base plate and seals two openings | [3M US catalogue (54 in x 60 yd rolls); DigiKey; Tekra; supplied cut by a converter](https://3m.com/3M/en_US/p/d/b40072050) | quote / quote | stock not seen: roll product; the converter supplies cut parts | low | 3M 93015LE (0.15 mm; would change the stack height) | **VERIFIED** 2026-11-11 |
| Transfer tape, cover-glass ring (also the sheet of the PA12 build) | 3M 9472LE | Thin film of glue, with no carrier, that holds the cover glass | [CS Hyde (12 x 12 in sheets); TestEquity; DigiKey; Zoro](https://catalog.cshyde.com/printitem/3m-products/3m-adhesive-transfer-tapes/3m9472le) | quote / quote | stock not seen: sheets and rolls listed at several US sellers | low | 3M 468MP (0.13 mm, a different adhesive family) | **VERIFIED** 2026-11-11 |
| Adhesive frame for the display, 0.15 mm foam type | 3M VHB 5906 (PROPOSED here; the design names no product) | Sticks the display under the roof ledge | [DigiKey (regional pages; the cut 5906-6-5 is DigiKey item 5039239); TapeCase through GoVets; JAM Industrial Supply; Motion](https://www.digikey.ca/en/products/detail/3m-tc/5906-6-5/5039239) | not seen / not seen | DigiKey India page: 63 in stock of the 6 in x 5 yd roll. GoVets (TapeCase cut): 2 in x 5 yd roll in stock at 53.29. Full 46 in x 72 yd rolls: 4,498.27 at JAM Industrial; list 9,625.54 at Motion (quote) | low | 3M 468MP (0.13 mm transfer tape, not a foam; rev 2, not re-checked) | **VERIFIED** 2026-11-13 |
| Opaque black double-coated tape for the baffle annulus (E16: 0.10 to 0.145 mm) | not selected. Candidates: 3M 9495B (0.145 mm); tesa 61361 (0.10 mm) | Blocks stray light under the baffle ring | [3M 9495B: Motion, TestEquity, JAM Industrial Supply (full rolls only). tesa 61361: no US seller found](https://www.testequity.com/product/10029445-7100064639) | quote / quote | 9495B: Motion lists a 27 in x 60 yd roll 'In Stock', quote required (list 1,835.66); JAM lists a 53.5 in x 180 yd roll at 5,099.46; an aggregator shows the 54 in x 60 yd roll at about 1,737 with zero stock. No sheets seen | medium: the tape with US listings (9495B) has only a thin black carrier between two clear adhesive layers, so light may travel sideways through it; for the tape whose adhesive is itself black (tesa 61361) no US seller was found | black liquid adhesive (the fallback named in mechanical/README) | **PROVISIONAL** 2026-11-13 |
| Cell fixing adhesive (E22: 0.06 mm or less) | 3M 467MP (PROPOSED here; the design names no tape) | Tacks the battery to the board | [TestEquity; Motion; Hisco; other 3M distributors](https://www.testequity.com/product/445-838-467MP-1) | not seen / not seen | stock not seen: the page shows no count. TestEquity: a narrow 60 yd roll at 70.46 each, 64.12 at 100 | low for supply. Design item: it is 0.058 mm without liner, so it passes E22's 0.06 mm by 0.002 mm and fails the 0.05 mm still written in master_params.yaml | 3M 9460PC: listings seen (JAM Industrial, Motion; wide rolls and case quantities at 1,153.89 to 2,156.97), but 3M's own US page gives it as 0.058 mm as well (the 0.05 mm on listing titles is a nominal figure), so it has no thickness advantage, and it is a permanent adhesive. Truly thinner: tesa 4972, 0.048 mm (one seller, US location unconfirmed: PROVISIONAL); 3M 82603, 0.03 mm (no US listing found: PROVISIONAL); 3M 82600, 0.005 mm (listing seen on a regional DigiKey page as a 1 m wide roll; price and stock not seen; fits on thickness only and is probably too thin to wet a cell pouch) | **VERIFIED** 2026-11-13 |
| Foam pad under the display, 0.3 mm | Rogers PORON 4790-92-30012-04P (0.30 mm, 26.6 x 10 mm cut) | Soft cushion that lets the battery swell without pushing on the display | [JBC Technologies (hosts the data sheet for this exact item); Stockwell Elastomerics; Modus Advanced: all converters, by quote](https://www.jbc-tech.com/media/1334/poron-4790-92-30012-p-extra-softslow-reboundsupported_jbc.pdf) | quote / quote | not seen: a converter item, with no price, stock, minimum order or lead time in any extract | medium: one special thin item in one density; no second 0.3 mm grade was found (in what was seen, PORON ShockSeal starts at 0.53 mm and ShockPad comes at 0.10 and 0.15 mm only) | None found at 0.3 mm. Two layers of 0.15 mm ShockPad, or a softer 0.5 mm PORON with a stack change, are not drop-ins. A 3M urethane foam was not searched | **PROVISIONAL** 2026-11-13 |
| Quarter-wave film for the sunglasses trial (EVT only; cut to dia 23.4 mm) | WP140HE, 100 x 100 mm sheet (Edmund Optics product page 44288; the stock number was not read) | A clear film under the cover glass that keeps the display readable through polarised sunglasses (the trial of amendments E9 and E19) | [Edmund Optics (Barrington, New Jersey), US web page](https://www.edmundoptics.com/p/100-x-100mm-4-retarder-film-wp140he/44288/) | 33.50 / not seen | stock not seen: the page shows no count | low for supply (one seller seen). Design item: the film has no adhesive, and its thickness is given two ways | American Polarizers APQW92-003-PC-140NM: 0.076 mm with a stated tolerance of +/-0.05 mm, so it can exceed E19's 0.11 mm; seen in a directory only, by quote (PROVISIONAL). Bolder Vision Optik: not found | **VERIFIED** 2026-11-13 |
| Optically clear adhesive for the quarter-wave film (EVT trial) | not selected (0.025 mm class optically clear transfer adhesive) | Bonds the quarter-wave film in place without clouding the view | not searched | not seen / not seen | not searched | open: no product has been looked for | none named | **PROVISIONAL** (not searched) |

Country of manufacture: not found for the lines above, except: Quarter-wave film for the sunglasses trial (EVT only; cut to dia 23.4 mm): Germany (Edmund data sheet).

Notes on these lines:

- **Adhesive sheet material, circuit board to base plate (FR-4 build)**: 0.20 mm (7.9 mil), polyester film carrier, 300LSE adhesive: this confirms the YAML thickness that was marked provisional. Die-cut pattern GL1-030.
- **Transfer tape, cover-glass ring (also the sheet of the PA12 build)**: 5.2 mil (0.13 mm) 300LSE transfer tape. CS Hyde lists a 12 x 12 in sheet at USD 6.33; TestEquity a 1/2 in x 60 yd roll at USD 17.92. Die-cut patterns GL1-033 (ring) and GL1-031 (PA12 build).
- **Adhesive frame for the display, 0.15 mm foam type**: 6 mil = 0.15 mm, confirmed by a listing title. The DigiKey sightings are on regional sites showing the same DigiKey item; the US page and a USD DigiKey price were not seen. The 2 in roll is enough for the EVT frames. Die-cut pattern GL1-032 with its vent channel. Design action A27.
- **Opaque black double-coated tape for the baffle annulus (E16: 0.10 to 0.145 mm)**: 3M 9495B: listings seen today (so the tape itself can be bought, as full rolls costing about 1,700 to 5,100 USD); 5.7 mil (0.145 mm) confirmed at TestEquity and on a 3M page. Construction per 3M: a 0.5 mil (0.013 mm) black polyester carrier coated on both sides with clear 200MP adhesive; 3M says the black film is there 'to provide opacity', but no transmission figure was seen. tesa 61361: 100 um, black PET with black acrylic adhesive, 'very good light-blocking properties' (maker's page); ask tesa tape, inc. (Charlotte, North Carolina) for a US converter. Black Nitto tapes: not checked. Buy cut parts from a converter (pattern GL1-034). Design action A24.
- **Cell fixing adhesive (E22: 0.06 mm or less)**: Sold as '2 mil'; one listing gives the thickness without liner as 2.3 mil (0.058 mm). The researcher's proposal to name 9460PC instead was refuted by the second check. The roll width on the TestEquity page was not confirmed (1.5 in in the summary, '-1' in the address). The price is per roll. Nitto 5600 series: not found. Design action A25.
- **Foam pad under the display, 0.3 mm**: This settles the doubt of rev 2: the item exists at 0.30 mm (0.012 in) as one specific code, seen on a converter-hosted data sheet, in Rogers' availability booklet and on a German converter's listing. It is the 30 lb/ft3 (480 kg/m3) density only; softer 4790-92 items start at 0.5 mm. It is cast on 0.05 mm PET film and has no adhesive; whether the 0.30 mm includes the PET is not stated. No compression-force figure for this item was seen (the nearest table stops at 400 kg/m3). Held at PROVISIONAL by the second check: a data sheet proves that the item exists, it is not a listing to buy. Design action A26.
- **Quarter-wave film for the sunglasses trial (EVT only; cut to dia 23.4 mm)**: New line (amendments E9, E19). Prices are per sheet: 33.50 each for 1 to 10, 29.10 for 11 or more. One sheet gives at most 16 discs of 23.4 mm. Thickness: 0.06 mm +/-0.003 on Edmund's product page, 53 +/-3 um on an Edmund-hosted data sheet that may be for a larger sheet: plan on 0.060 until a sheet is measured. Retardance 147 +/-4 nm; transmission above 89 %. The fast axis is marked by a black stripe on the protective film, which is removed before use. Design action A23.
- **Optically clear adhesive for the quarter-wave film (EVT trial)**: New line. E19 limits the film with its adhesive to 0.11 mm, and the film found has none. With the film at 0.063 mm worst case, 0.047 mm is left: a 0.025 mm adhesive fits (0.088 mm in all), a 0.05 mm one does not (0.113 mm). Design action A23.

---

## 7. Adhesives, by class

The design names what each glue must do, not which product to use. The first table restates each class. The second names
**candidates**: real products whose data sheets, as far as they were seen, come close, and for which a US seller was looked
for (the Status column says whether a listing was seen: 14 of the 22 are VERIFIED). **A candidate is a starting point for a
coupon test** (a trial bond on small sample pieces of the real materials), **not a selection.** No candidate has been tested
on this product's materials (vapor-smoothed nylon PA12, solder mask, routed FR-4, glass). The four classes that had no
priced candidate in rev 2 (rim sealant, prism adhesive, primer, thermal adhesive) now have at least one.

| Adhesive class | What it does | What the design asks for, and remarks | Candidates | Supply and technical risk | Status |
|---|---|---|---|---|---|
| Perimeter seal adhesive (class) | The black glue bead that seals the base to the shell (about 70 mm3 per marker) | Requirement (mechanical/README): opaque black, thixotropic, work life 1 h or more, cures at room temperature or 45 C at most, sustained peel at 70 C on primed PA12 and on FR-4 solder mask. | candidates: 3M Scotch-Weld DP490; Huntsman Araldite 2031-1 (3M DP420NS Black fails the work-life need) | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-11 |
| Ball-foot potting epoxy (class) | Locks each ball foot in its hole (stage 1 dual-cure or two-part; stage 2 two-part, room temperature) | Stage 2 cures between two opaque boards, so light cannot reach it. About 1 mm3 per foot. Stage 1 needs an epoxy thin enough to run round and under a 1.0 mm ball in a 1.10 mm hole. If silicon nitride balls are used, adhesion to them must be tested too. | candidates: Loctite EA E-30CL; EPO-TEK 301; 3M Scotch-Weld DP460 Off-White (now VERIFIED; stage 2 only unless its viscosity is shown to suit stage 1); stage 1 option Dymax Multi-Cure 6-621-GEL | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-13 |
| Visor-window adhesive, thixotropic light-cure (class) | A gel that is cured with light; it frames each window without creeping behind the glass | Must not wick: adhesive at the roof edge of the opening would clip the cameras' upper field. About 1 mm3 per window. Design action A31. | candidates: Dymax Multi-Cure 6-621-GEL (single syringes, about a month's lead); Dymax 3094-GEL (only in packs of 20). Dymax 3022-GEL: no US listing found on two search days, drop it | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-13 |
| Clear optical potting for the grain opening (class) | Clear, hard fill that keeps mud and dew off the grain LEDs and photodiode (about 0.1 ml per marker) | Requirement: clear, low fluorescence, non-yellowing, mixed viscosity about 0.1 to 2 Pa.s, cure at 60 C at most, low shrinkage, chosen modulus. Potting is step 12 and the cell is fitted in step 13, so the limit here is the 60 C set for the adhesive sheet and the PA12 ring, not the cell's 45 C. Design action A30. | candidates: EPO-TEK 301 (recommended cure 65 C); Master Bond EP30-2 (room-temperature cure given as normal; mixed viscosity unknown). EPO-TEK 301-2 (recommended cure 80 C) should be removed | low for supply; high technical risk: no candidate has a maker-recommended full cure at or below the 60 C limit of assembly step 12, and 'low fluorescence' is not documented for any of them | **PROVISIONAL** 2026-11-13 |
| Hood gasket bead, black, soft, silicone-free (class) | Soft bead that closes the slit above each camera against stray light | Requirement: black, about Shore A 40, silicone-free, form-in-place, holds a 0.5 x 0.33 mm bead. No candidate is confirmed opaque black. | candidates: Dymax GA-140 (Shore A35); Dymax GA-112 (Shore A50, 'black translucent'); Dymax GA-142 (softer) | low for supply; high technical risk until coupon tests are done (nothing is proven on vapor-smoothed PA12 or solder mask) | **PROVISIONAL** 2026-11-11 |
| Cover-glass rim sealant, black, wicking grade (class) | Thin black sealant that runs into the 0.25 mm gap round the cover glass | The gap is 0.25 x 1.13 mm; about 25 mm3 per marker. The sealant goes on in assembly step 5, before the window adhesive, the vent, the gaskets, the display frame and the perimeter seal are bonded, which is why a silicone needs a decision: the design asks for silicone-free materials elsewhere. Design action A32. | candidates: MG Chemicals 832FX-450ML (black epoxy, silicone-free, 88 Shore A as listed); Dow SE 9187 L Black (silicone, Shore A 17). Do not order MG 832FXT: it is the anti-wicking grade | medium: two candidates now exist, but neither meets every requirement. The silicone-free one cures stiff; the one that meets every stated property is a silicone | **PROVISIONAL** 2026-11-13 |
| Prism bonding adhesive, UV-cure (class) | Tacks each prism to its camera at four corners | No shrinkage figure was seen for either candidate, so 'low shrink' is unconfirmed. Assembly step 13 comes after the cell is on the board: the UV lamp must not warm the unit above 45 C. | candidates: Norland NOA 61 (VERIFIED, priced); Norland NOA 68 (better on plastics; PROVISIONAL) | low for supply; technical risk until tried: whether a thin liquid stays as four corner dots, and what the top of the camera cube is made of, are not known | **PROVISIONAL** 2026-11-13 |
| Primer or plasma treatment for the nylon bonding faces (class) | Prepares the printed nylon so that tapes and glues grip it | Treat a primer as covering the tape joints only (cover-glass ring, display frame, the sheet of the PA12 build) until 3M's guidance for its 300LSE tapes on nylon has been read and each liquid-adhesive maker has been asked. Design action A34. | candidates: 3M Tape Primer 94; 3M Adhesion Promoter 111. Plasma or corona treatment by the printing bureau: not searched | low for supply; open technically: both candidates are sold as tape primers, and nothing seen says that 3M recommends either on nylon (PA12) or under an epoxy or a light-cure adhesive | **PROVISIONAL** 2026-11-13 |
| Thermal adhesive for the two temperature sensors (class) | A dab that couples each temperature sensor to the cell | Two dabs of about 1 mm3 per marker, applied in assembly step 13, after the cell: no heat above 45 C. Longer-working siblings: 8329TFS-25ML (data sheet seen, cure time not seen) and 8329TFM-25ML (45 minutes working, 24 h cure; no US listing seen today). Design action A33. | candidates: MG Chemicals 8329TFF-25ML (VERIFIED, priced, 5-minute working time); MG 8329TCS-6ML (listing only; cure time not seen). Rejected: MG 8329TCM-6ML (no longer manufactured); Arctic Silver AATA-5G (out of stock at both US sellers seen, one listing marked discontinued) | low for supply; one check before release: the adhesive must be an electrical insulator, because each dab lies across a sensor's two terminals | **PROVISIONAL** 2026-11-13 |

### Candidates (not selections)

| Class and candidate | Product | Maker | US source | Stock or lead time as seen | Data-sheet properties and remarks | Status |
|---|---|---|---|---|---|---|
| Perimeter seal, candidate A | 3M Scotch-Weld DP490 (black) | 3M | [3M US catalogue (400 mL cartridge, 6 per case); 50 mL cartridges seen only at Farnell (Europe)](https://www.3m.com/3M/en_US/p/d/v101722005/) | not found | Data-sheet properties seen: black, thixotropic gap-filling two-part epoxy, mix 2:1, work life 90 min, room-temperature cure (test data after 7 days at 23 C), temperature resistance to 120 C, bell peel 34.5 N/cm (Canadian data sheet). On paper it meets colour, thixotropy, work life and cure limit. Not tested on PA12 or solder mask. Confirm a 50 mL pack in the US. | **VERIFIED** 2026-11-11 |
| Perimeter seal, candidate B | Araldite 2031-1 | Huntsman | [Chemical Concepts; Perigee Direct (50 mL)](https://www.chemical-concepts.com/product/aralditer-2031-epoxy-adhesive/) | not found | Black, toughened, thixotropic (non-sag to 10 mm), mix 1:1, room-temperature cure, pot life 60 to 70 min for 100 g (Huntsman comparison sheet), described as having good adhesion on polyamides. The peel table was not readable in the extract. | **VERIFIED** 2026-11-11 |
| Perimeter seal, candidate C (benchmark; fails the work-life need) | 3M Scotch-Weld DP420NS Black | 3M | [3M US catalogue; gluegun.com](https://eaa.3m.com/3M/en_US/p/d/b40066483/) | not found | Black, toughened, non-sag, 2:1, work life 20 min (the design asks for 1 h or more), handling strength in about 2 h, full cure in 24 h at 22 C. | **VERIFIED** 2026-11-11 |
| Ball potting, candidate A | Loctite EA E-30CL | Henkel | [Ellsworth Adhesives (200 mL cartridge); Perigee Direct](https://ellsworth.com/products/adhesives/epoxy/henkel-loctite-hysol-e-30cl-epoxy-adhesive-clear-200-ml-cartridge) | not found | Clear, low viscosity, two-part 2:1, 30 min work life, full cure in 24 h at room temperature, lap shear 21 N/mm2 on grit-blasted steel (Henkel data sheet, January 2018). | **VERIFIED** 2026-11-11 |
| Ball potting, candidate B; clear potting, candidate A | EPO-TEK 301 | Epoxy Technology (Meridian Adhesives) | [Fiber Optic Center (4 g and 8 oz kits)](https://media.focenter.com/CMP1007/files/EPOTEK301SpectrallyTransparentEpoxyRoomTemperatureCure8oz_ET301-8OZ_fiberopticcenter_REV2.pdf) | not found | Two-part, very low viscosity, mix 20:5 by weight, pot life 1 to 2 h, cure 65 C for 1 to 2 h or 23 C for 24 h, transmission 99 % or more from 382 to 980 nm, refractive index 1.519. Viscosity value, hardness, shrinkage and fluorescence were not seen. Cure data seen on 2026-11-13 (data sheet Rev IX, March 2015): 'Recommended Cure: 65 C / 2 Hours'; 'Minimum Alternative Cure(s): Note: May not achieve performance properties below; 65 C 1 Hour; 23 C 24 Hours'; total mass not to exceed 25 g. So the maker's recommended cure is 5 C above the 60 C limit of step 12, and the room-temperature cure is hedged. The second check confirmed the 65 C line and saw a viscosity of 100 to 200 cP at 23 C on a sheet of the 301 family (possibly a sister sheet). Downgraded to PROVISIONAL in the review, without a new search (date kept): the evidence is a data sheet on the seller's server, not a listing with a price or stock. | **PROVISIONAL** 2026-11-11 |
| Ball potting, candidate C | 3M Scotch-Weld DP460 Off-White, 50 mL Duo-Pak (3M ID 7100148768) | 3M | [Hisco; TestEquity; also listed by JAM Industrial Supply, Hillas, EIO and Boeing Distribution](https://www.hisco.com/Product/DP460-50ML-31180) | Hisco: 38 in stock (snapshot) | Hisco: 52.62 per cartridge, sold in 12-count cases. TestEquity: 52.62 each, 44.73 at 25. Work life 60 minutes (60 to 90 on some listings), handling strength in about 4 h. Off-white and opaque, which is fine between two opaque boards. Its viscosity was not seen; from memory it is a thick paste, so keep it for stage 2 unless the data sheet shows it can fill stage 1. A Duo-Pak also needs 3M's EPX applicator and mixing nozzles (not priced). Do not confuse it with DP460NS (non-sag, 3M ID 7100148751). Prices are per cartridge, not per marker. | **VERIFIED** 2026-11-13 |
| Window adhesive, candidate A (also a stage-1 option for the ball feet) | Dymax Multi-Cure 6-621-GEL, 30 mL syringe | Dymax | [TestEquity (10000994-6-621-30ML); Jensen Tools (same listing)](https://www.testequity.com/product/10000994-6-621-30ML) | TestEquity: 23-day manufacturer lead time, so not on the shelf | Light-cure gel that also cures with heat or an activator in shadowed areas; Dymax names metal, glass, ceramic, phenolic and filled polyamide; adhesion to unfilled, vapor-smoothed PA12 is not shown. Price per 30 mL syringe: 112.77 on one TestEquity page, 121.52 on another (which says pricing may not reflect the latest surcharges); 99.24 each at 100 syringes on 2026-11-11. Allow about a month. | **VERIFIED** 2026-11-13 |
| Window adhesive, candidate B | Dymax 3022-GEL | Dymax | not found | not found | NOT FOUND: two more searches today (one naming Ellsworth and TestEquity, one with the exact number in quotes) returned no listing at any seller, as on 2026-11-11. One search summary suggests the number may be wrong or the product discontinued. Drop it, or ask Dymax whether 3022-GEL is a current grade. | **PROVISIONAL** 2026-11-13 |
| Window adhesive, candidate C | Dymax Ultra Light-Weld 3094-GEL, 30 mL MR syringe (sold in packs of 20) | Dymax | [Ellsworth Adhesives](https://www.ellsworth.com/products/by-manufacturer/dymax/adhesives/uv-curing/dymax-ultra-light-weld-3094-gel-uv-curing-adhesive-yellow-30-ml-mr-syringe/) | 'New Limited Availability'; typical ship time 21 to 30 business days; no cancellations or returns | Correction to rev 2: the price of 1,186.75 that rev 2 flagged as a possible error is a pack of 20 syringes (59.34 each). For a 10-unit build that is a non-returnable order of about 1,187 dollars and a wait of 4 to 6 weeks. Thixotropic, low-stress plastic bonder, yellow; glass is not named (rev 2). Single US source seen. | **VERIFIED** 2026-11-13 |
| Clear potting, candidate B | EPO-TEK 301-2 | Epoxy Technology (Meridian Adhesives) | [Fiber Optic Center; Meridian Adhesives](https://products.meridianadhesives.com/storage/downloads/xjagq6xi1luav3sdwj9yuwpee21igy91/301-2-rev-xviii-2.pdf) | not found | Optical grade, low viscosity, long pot life. Recommended cure 80 C for 3 h; 'minimum alternative' 23 C for 48 h, which may not reach the data-sheet properties. The 80 C cure is above the 60 C limit of assembly step 12. Fluorescence data not found. Confirmed again on 2026-11-13 by two searches: recommended cure 80 C / 3 hours, 20 C above the limit of step 12; pot life 8 h. Remove it from the candidates unless the maker states in writing what a 23 C or a 60 C cure gives. Downgraded to PROVISIONAL in the review, without a new search (the row keeps its 2026-11-11 date): the evidence is a data sheet, with no price, pack or stock seen. A data sheet shows that a product exists; it is not a listing to buy. | **PROVISIONAL** 2026-11-11 |
| Clear potting, candidate C | Master Bond EP30-2 | Master Bond | [Master Bond, direct, by quotation (that it is a US company is from memory)](https://datasheets.globalspec.com/ds/Master-Bond/ep30-2/bc0f0830-873b-4300-aa6f-c24a19ca3650) | not seen (sold by quotation; no price, pack size or stock) | Downgraded from VERIFIED by the second check: the link is a directory copy and there is no price, pack or stock. The maker says it 'cures readily in 24-48 hours at room temperature or more rapidly at elevated temperatures, e.g. 2-3 hours at 150-200 F', the only candidate whose room-temperature cure is given without a caveat. The 'optimum cure' that adds 2 to 3 h at 150 to 200 F (66 to 93 C) may belong to the variant EP30-2LB. Mixed viscosity unknown: the variant's part A is 10,000 to 16,000 cP, so the mix could exceed the 2 Pa.s (2,000 cP) the design allows. Mix ratio 10:1 by weight on most sources. Fluorescence not seen. Ask Master Bond for the mixed viscosity and for properties after a room-temperature cure. | **PROVISIONAL** 2026-11-13 |
| Hood gasket, candidate A | Dymax GA-140 | Dymax | [Dymax, direct or through its distributors (US-headquartered company, from memory; country of manufacture not found)](https://dymax.com/products/formulations/light-curable-materials/gasketing) | not found | UV-cure form-in-place gasket, Shore A35, silicone-free, soft and tack-free. Colour not found: the design needs an opaque black bead. Downgraded to PROVISIONAL in the review, without a new search: the evidence is the maker's own product page, with no US seller, price, pack or stock seen, and that Dymax sells from the US is from memory. | **PROVISIONAL** 2026-11-11 |
| Hood gasket, candidate B | Dymax GA-112 | Dymax | [Dymax, direct or through its distributors (US-headquartered company, from memory; country of manufacture not found)](https://aleo.dymax.com/products/formulations/light-curable-materials/gasketing/ga-112) | not found | Shore A50, silicone-free, listed as 'black translucent' in a Dymax brochure. Harder than the Shore A 40 target, and translucent: a light-leak test is needed. Downgraded to PROVISIONAL in the review, without a new search: the evidence is the maker's own product page, with no US seller, price, pack or stock seen, and that Dymax sells from the US is from memory. | **PROVISIONAL** 2026-11-11 |
| Hood gasket, candidate C | Dymax GA-142 | Dymax | [Dymax, direct or through its distributors (US-headquartered company, from memory; country of manufacture not found)](https://dymax.com/products/formulations/light-curable-materials/gasketing/ga-142) | not found | Shore 00-55 (much softer than Shore A 40), silicone-free. Colour not found. Downgraded to PROVISIONAL in the review, without a new search: the evidence is the maker's own product page, with no US seller, price, pack or stock seen, and that Dymax sells from the US is from memory. | **PROVISIONAL** 2026-11-11 |
| Rim sealant, candidate A (silicone-free) | MG Chemicals 832FX-450ML (black flexible epoxy, 450 mL kit) | MG Chemicals | [TestEquity (stock no. 10001466); Master Electronics (listing link)](https://www.testequity.com/product/10001466-832FX-450ML) | TestEquity: manufacturer lead time 14 days, so probably not on the shelf. An aggregator copy shows DigiKey with 9 in stock at 64.44 (unverified) | TestEquity: 71.46 each at 1, 62.88 at 100. Black two-part epoxy, 1:1 by volume, mixed viscosity 700 cP at 25 C (confirmed by a second source), about 150 minutes of working time, cures at room temperature. Cured hardness listed as 88 Shore A, which is stiff for a seal called flexible; the second check could not confirm that figure. Not seen: wicking into the gap, adhesion to glass and to PA12, the cure time. One kit is about 18,000 rim seals, so shelf life and not quantity sets the cost; no pack smaller than 450 mL was seen. It must be mixed and loaded into a syringe, and it stays liquid in the gap for hours: the tub must stay level. Read hardness and cure time in MG's data sheet before the decision. | **VERIFIED** 2026-11-13 |
| Rim sealant, candidate B (silicone) | Dow SE 9187 L Black, 330 mL cartridge | Dow (DOWSIL) | [Ellsworth Adhesives (330 mL cartridge; an 18 kg pail is also listed)](https://ellsworth.com/products/conformal-coatings/silicone/dow-se-9187-l-silicone-conformal-coating-black-330-ml-cartridge) | price and stock not seen | VERIFIED as a listing only: Ellsworth's price and stock were not in the extract (the one price seen, 108.54 for a cartridge, is from a non-US Farnell site). Black, one part, 1,100 cP, cures at room temperature in 24 to 72 h, tack-free in about 8 minutes, Shore A 17, 160 % elongation: it meets every stated property. But it is a silicone, applied before the later bonds are made. A cartridge begins to cure once opened; 330 mL against 25 mm3 per marker. | **VERIFIED** 2026-11-13 |
| Prism adhesive, candidate A | Norland NOA 61, 1 oz bottle | Norland Products | [Edmund Optics (US site); Thorlabs; Fisher Scientific (listing link)](https://www.edmundoptics.com/p/1-oz-application-bottle-of-noa-61/4209/) | Thorlabs: 'Available/Ships: Today' (undated snapshot). Edmund: stock not in the extract | Edmund Optics US: 38.00 each for 1 to 4, 35.00 for 5 to 11, 26.00 for 12 or more (the price cell holds the 5-to-11 figure). Thorlabs: 40.70. Refractive index 1.56, 300 cP at 25 C. No shrinkage figure seen. The price is per 1 oz bottle, which covers any build considered here. | **VERIFIED** 2026-11-13 |
| Prism adhesive, candidate B (better on plastics) | Norland NOA 68, 1 oz bottle | Norland Products | [Edmund Optics US (the 1 oz page appeared only as a result link); Fosco Connect (its own number T-NOA68, 68.00; that it ships from the US is from memory)](https://www.edmundoptics.com/p/1-oz-application-bottle-of-noa-68/4178/) | not seen | Downgraded by the second check: the Edmund extract was for the 1 lb bottle and gave no US price for the 1 oz bottle. The maker says it gives improved adhesion to plastics such as acrylic and polycarbonate, which matters if the top of the camera cube is plastic (not known). Refractive index 1.54. Viscosity and shrinkage not seen. | **PROVISIONAL** 2026-11-13 |
| Primer, candidate A (tape primer) | 3M Tape Primer 94, 0.66 mL ampule (1/2 pint can: 3M ID 7100003278) | 3M | [Ellsworth Adhesives; Hisco; Uline; FindTape; RSP Supply](https://www.ellsworth.com/products/by-manufacturer/3m/surface-preparation-materials/primer/3m-94-tape-primer-0.66-ml-ampule/) | Ellsworth: ampule in stock. Hisco: 25 half-pint cans in stock (snapshots) | Ellsworth: 2.56 per ampule for 1 to 113. Hisco: half-pint can 26.07. Ellsworth: 1 gal can 259.52. Sold everywhere as a TAPE primer; whether 3M recommends it on nylon or under an epoxy was not in any extract. Uline says its quart is restricted in several states. | **VERIFIED** 2026-11-13 |
| Primer, candidate B (adhesion promoter) | 3M Adhesion Promoter 111, 250 mL bottle (3M ID 7000001323) | 3M | [Ellsworth Adhesives; Hisco and Global Industrial (listing links); Motion (1 gal); Beach Audio (case of 4)](https://www.ellsworth.com/products/by-manufacturer/3m/surface-preparation-materials/primer/3m-111-adhesion-promoter-250-ml-bottle/) | Ellsworth: in stock, usually ships in 1 to 2 business days (snapshot) | Ellsworth: 35.05 for 1 to 5, 26.98 for 6 to 37, 25.37 for 38 or more (the price cell holds the 6-to-37 figure). A clear, alcohol-based adhesion promoter. Whether 3M recommends it on nylon or under an epoxy was not in any extract. One bottle is far more than a 10-unit build needs. | **VERIFIED** 2026-11-13 |
| Thermal adhesive, candidate A | MG Chemicals 8329TFF-25ML (fast-cure thermally conductive epoxy, 25 mL dual syringe) | MG Chemicals | [Hisco; TestEquity (stock no. 10001428); DigiKey and Mouser (through an aggregator); Master Electronics (listing link)](https://www.hisco.com/Product/8329TFF-25ML-33018) | Hisco: 9 in stock. TestEquity: 10-day manufacturer lead time. Aggregator copy: DigiKey about 81 to 88 in stock, Mouser 111 | Hisco: 34.89. TestEquity: 36.63 at 1, 32.23 at 200. Two-part epoxy, so silicone-free; 0.8 W/(m.K) and a 5-minute working time (both confirmed from MG's data sheet by the second check); cure 4 h at room temperature or 15 minutes at 65 C (researcher's extract; not re-seen). 'Provides strong electrical insulation' was seen only as a feature line: read the volume resistivity before release. A sheet hosted by Farnell gives 72,000 and 110,000 cP for the two parts, so it is a paste that stays where it is dabbed. With 5 minutes of working time, mix a little and do one unit at a time. | **VERIFIED** 2026-11-13 |
| Thermal adhesive, candidate B | MG Chemicals 8329TCS-6ML (slow-cure thermally conductive epoxy, 6 mL syringe) | MG Chemicals | [DigiKey (473-1221-ND; regional pages)](https://www.digikey.co.uk/en/products/detail/mg-chemicals/8329TCS-6ML/6035512) | price and stock not seen | VERIFIED as a listing only, on regional DigiKey sites carrying the same DigiKey number: listed as active, 1.40 W/m-K, shelf life 36 months. A US price 'from 38.04' appeared only in a search summary. Its cure time at room temperature and its electrical insulation were not seen; from memory this grade takes days to cure, which would hold up assembly steps 14 and 15. Do not treat it as an orderable alternative until the cure time has been read. | **VERIFIED** 2026-11-13 |

What the candidate search showed:

- **Perimeter seal** (not re-checked). Only two products seen meet "black, thixotropic, an hour or more of work life,
  room-temperature cure" on paper: 3M DP490 and Araldite 2031-1.
- **Ball-foot potting.** 3M DP460 was seen in stock and priced, but its viscosity was not seen, and the first of the two
  potting stages needs a thin epoxy (A35).
- **Visor-window adhesive.** Of the three candidates, one was not found at any US seller on two search days (Dymax
  3022-GEL), one is sold only in a pack of 20 syringes for about USD 1,187 (3094-GEL), and one can be bought singly with
  about a month's wait (6-621-GEL). For a 10-unit build that leaves one practical choice (A31).
- **Clear potting.** No candidate has a maker-recommended full cure at or below the 60 C limit of assembly step 12. EPO-TEK
  301 asks for 65 C; EPO-TEK 301-2 for 80 C; Master Bond EP30-2 gives a room-temperature cure as normal, but nothing else
  about it was confirmed. **No fluorescence figure was found for any of them**; it has to be measured (A30). None of the
  three is VERIFIED as a listing: for each, only a data sheet or a directory copy was seen.
- **Hood gasket** (not re-checked). The soft silicone-free light-cure gaskets seen are clear or "black translucent", not
  opaque black. Only the maker's own pages were seen, so the three candidates are PROVISIONAL.
- **Cover-glass rim sealant.** Two candidates, and a choice between them that only the designers can make: a silicone-free
  black epoxy that cures stiff, or a soft black silicone that meets every stated property but brings silicone into a build
  that avoids it elsewhere (A32).
- **Prism adhesive.** Norland NOA 61 is listed at two US optics houses at USD 38 to 41 a bottle; one of them showed it ready
  to ship. Whether a liquid this thin stays as four corner dots has to be tried.
- **Primer.** Two 3M primers are cheap and were seen in stock, but both are sold for tapes; nothing seen recommends either
  on nylon or under a liquid adhesive (A34).
- **Thermal adhesive.** One good candidate (MG Chemicals 8329TFF) and two dead ends: a sister grade that is no longer
  manufactured and a hobby product that is out of stock (A33).

---

## 8. Custom parts and outside services

Nothing in this section was checked again on 2026-11-13: the search allowance went to the catalogue parts. Every line keeps
its 2026-11-11 date and its rev 2 wording, with one addition on the cradle board. No price was published for any of this
work; every figure used for it in section 10 is an assumption. VERIFIED on a line of this section means only that a US
company was seen advertising that kind of work: no company was asked whether it will take this job.

| Item | Part number | What it is for | US source | Price at 10 / at 1000 (USD each) | Stock or lead time as seen | Supply risk | Alternative | Status |
|---|---|---|---|---|---|---|---|---|
| Main circuit board, bare (4 layers, 0.8 mm, ENIG, 0.10 / 0.10 mm in the fine areas, through vias) | custom (Gerber set; outline GL1-040) | The board that carries every electronic part | [Bay Area Circuits (Fremont, California); Sierra Circuits (Sunnyvale, California); AdvancedPCB (custom service)](https://bayareacircuits.com/pcb-capabilities/) | quote / quote | Sierra advertises turn times from 1 day; others not seen | low to medium: the capability is published, but 0.100 mm is 1.6 um under '4 mil' (0.1016 mm), plugged-and-covered vias were not found in any published tier, and the standard-tier figure may hold for outer layers only (reported in review, not re-checked) | Summit Interconnect / Royal Circuits (advanced tier) | **VERIFIED** 2026-11-11 |
| Circuit-board assembly (both sides, two camera cubes, LGA sensor, 64-pin processor, 0402 parts) | service | Machine-placing and soldering the parts onto the board, with X-ray of the hidden joints | [MacroFab (Houston, Texas); AdvancedPCB assembly; Sierra Circuits (turnkey)](https://www.macrofab.com/pcba/) | quote / quote | Sierra advertises turnkey boards in as fast as 5 days; others not seen | medium: the camera cubes are reflowed with their lenses on, need X-ray, and their land pattern is still unverified | Screaming Circuits; CircuitHub (capabilities not found today) | **VERIFIED** 2026-11-11 |
| Base plate, routed 0.80 mm FR-4, no copper, matte black mask (drawing GL1-011) | custom (drawing GL1-011 and its fab files) | The flat underside of the marker; carries the ball feet | [Bay Area Circuits; Sierra Circuits; AdvancedPCB (to be asked with the drawing)](https://bayareacircuits.com/pcb-capabilities/) | quote / quote | not found | low | printed PA12 plate GL1-012 (the documented alternative build) | **PROVISIONAL** 2026-11-11 |
| Base plate, alternative build: printed PA12, 0.87 mm, with integral baffle (drawing GL1-012) | custom (drawing GL1-012) | The same underside plate, printed in nylon: for the 4 EVT units and the shells of the all-printed comparison | [Protolabs; Xometry; Fictiv; Hubs (Protolabs Network): the bureaus of the tub line, to be asked with the drawing](https://www.protolabs.com/services/3d-printing/multi-jet-fusion/) | quote / quote | not found | medium: bureaus quote +/-0.2 to 0.3 mm, which is wide for a 0.87 mm plate whose thickness and flatness set the height of the ball feet; earlier research expects thin printed discs to warp 0.2 to 0.5 mm (unverified) | the FR-4 plate GL1-011 (the primary build) | **PROVISIONAL** 2026-11-11 |
| Cradle circuit board (2 layers, 1.0 mm, 30 x 22 mm) and its assembly | custom | Small board that carries the USB-C socket and the spring pins | [OSH Park (2-layer prototype service) or any US board shop](https://oshpark.com/pricing) | quote / quote | not found | low | any US 2-layer board service | **PROVISIONAL** 2026-11-11 |
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
- **Cradle circuit board (2 layers, 1.0 mm, 30 x 22 mm) and its assembly**: OSH Park's 2-layer price is from memory (about USD 5 per square inch for three boards); today's search showed only its 4-layer price (USD 10 per square inch for three). Since rev 2 the cradle has a netlist and a bill of materials (7 lines; section 4). Rev E: the board is 1.0 mm thick (amendment E36; 1.6 mm before) and its seven spring-pin holes are 0.80 mm finished for the 0.635 mm tail (design action A6 applied in electrical/gl1_cradle; the 0.90 mm drills of the earlier set are gone). Still open: the mechanical model draws a 0.90 mm hole and a 0.76 mm tail, and the tail length (about 1.34 mm) is PROVISIONAL. Whether a prototype service offers a 1.0 mm board at its usual price was not checked.
- **3D printing of the tub (HP Multi Jet Fusion PA12, dyed black, vapor smoothed)**: Published figures: Protolabs MJF minimum wall 0.020 in (0.508 mm), minimum feature 0.02 in, parts dyed black, vapor smoothing offered for PA12 black (roughness from 250+ down to 64-100 uin Ra) with a 0.030 in (0.762 mm) minimum wall; Xometry +/-0.3 % with a floor of +/-0.2 or 0.3 mm and about 1 mm minimum wall for smoothing; Fictiv +/-(0.3 mm + 0.002 mm/mm) and 'walls under 1.5 mm do not smooth as uniformly'; Hubs 0.7 mm supported walls. Reported in review, not re-checked: a second Protolabs page (its UK Multi Jet Fusion page) asks for a 1.5 mm minimum wall 'for proper smoothing'. Protolabs' own MJF tolerance was not seen. Xometry, Fictiv and Hubs pass orders to partner shops: ask for US production in writing.
- **3D printing of the baffle-ring sets (MJF PA12, dyed black, not smoothed)**: Printed as sprued sets of six; lapped to height in-house.
- **3D printing of the cradle body (MJF PA12, not smoothed, not tumbled)**: 27 cm3; the build direction is locked and must be confirmed on the order.
- **Die cutting of the adhesive parts (patterns GL1-030, -031, -032, -033, -034)**: 3M states that converters use laser, water jet and plotters for small prototype runs; Strouse advertises tool-free digital converting; Marian lists laser cutting and rapid prototyping. No minimum order or price was seen. GL1-031 is the sheet of the PA12 build (0.13 mm transfer tape cut with the baffle pattern); 4 of the 10 EVT units and half of the extra shells need it.
- **Glass cutting and finishing service**: The cost is carried on the visor-window and production cover-glass lines.
- **Fixtures: laser-cut and sheet parts (nests, masks, press plates)**: Laser tolerance +/-0.005 in on metal parts under 12 in and about +/-0.009 in on plastics. Its page says all cutting is done at its own sites in Nevada, Kentucky and Texas; where the sheet material is made is not stated. Fixture cost is kept out of the per-unit figures (see the roll-up).
- **Fixtures: precision machined gauges (ball gauge plate with reamed 0.60 mm holes, lapping gauge, go gauges, dummy unit, calibration nest)**: Needs grinding and reaming beyond laser-cut accuracy. Also to buy: granite surface plate, positive-displacement dispenser, vacuum bell, UV lamp, pogo test block, leak-test chamber. Budget in the roll-up.
- **FCC Part 15 Subpart B emissions test (unintentional radiator, Class B)**: The GL-1 has no radio, so it follows the Supplier's Declaration of Conformity route: test, keep the report, name a US responsible party. Cost figures seen: USD 800 to 2,000 for testing alone, 1,500 to 5,000 with documentation (from a low-reliability guide site and lab marketing pages: get quotes). Test the marker in its cradle with a USB cable and charger attached. One-time cost, not in the per-unit figures.
- **Selective hard gold on the contact pads (production boards only)**: Not published as a standard-tier option by any fabricator checked. Its cost is assumed inside the q1000 bare-board figure.

The two tables below are carried unchanged from rev 2 (2026-11-11); nothing in them was re-checked on 2026-11-13.

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

Facts seen on 2026-11-13 unless a row says "rev 2", which means seen on 2026-11-11 and not checked again.

At a glance:

| # | Risk | Why it matters, with the facts of 2026-11-13 | What to do |
|---|---|---|---|
| 1 | **Camera cube OVM7692-RYAA** (2 per marker) | One maker and one authorised US distributor (DigiKey). DigiKey's own pages showed 1,814 and 2,497 in stock, about what 1000 markers need (2,000 plus losses) or less. Nothing else drops into its place: the camera bay, the prism height and the light hoods are built round this cube. No end-of-life notice was found in two independent searches, but no statement from the maker was seen either, and a sibling variant is listed obsolete. Prices are now seen on DigiKey's own page: USD 27.50 for one, USD 6.25 each on a full reel of 2,500 (the tape-and-reel pack that assembly machines take), nothing in between. | (a) Ask OmniVision or DigiKey for a written life-cycle statement and a quote at 100 and at 2,000 before the layout is frozen. (b) Buy the cubes for the first two builds now. (c) For any build above about 800 markers, plan on one full reel of 2,500 (about USD 15,600 at the reel price) and a 20-week wait. |
| 2 | **Sharp LS013B7DH03 display** | One maker, no drop-in second source, 28-week factory lead time. Shelf stock is **not established**: undated copies of DigiKey's page seen today range from 0 to 32,134 pieces; Arrow showed about 1,383; Future none, with a minimum order of 2,240. DigiKey lists the part as Active and no Sharp notice was found; one old Mouser page and one reseller call it obsolete. The price at 10 seen today is USD 9.60 (it was 8.82 two days earlier). | (a) Read the live DigiKey and Arrow pages, or phone, and order the build quantity before any other part. (b) Ask Sharp or DigiKey for the life-cycle status in writing. (c) Settle the thickness (0.741 mm in today's extracts, 0.746 mm in the design) from the Sharp drawing. (d) For production, order seven months ahead. |
| 3 | **Lithium-polymer cell, 2 x 10 x 30 mm, with protection board** | One US seller (PowerStream, Utah). Listed at USD 12.00 each; no stock figure and no lead time; the site says cells with an order button are kept 'for sample quantities'; one extract dates the page September 2024. Three searches found no second US seller of a protected cell of this size. The protection board is fitted only when it is asked for. | (a) Ask PowerStream now for a dated quote, stock, lead time, volume prices, the data sheet and the safety papers, and for the name of the cell maker. (b) Order in writing as GM201030-PCB; buy 20 to 30 cells and measure them. (c) Do not count on the same seller's PGEB021235: it does not fit this board (section 12.2). |

### 9.1 Camera cube: OmniVision OVM7692-RYAA

A camera cube is a complete tiny camera, sensor and lens in one block of 2.95 x 3.47 x 2.76 mm, that is soldered to the
board like a chip. Each marker has two.

| Question | What was found | Source and status |
|---|---|---|
| Is it still made? | No end-of-life, last-time-buy, "not recommended" or change notice was found in two independent searches. DigiKey: 'Part Status Active'. A broker page (PCX) also says Active. Findchips gives the life-cycle code as 'Contact Manufacturer'. OmniVision's product brief v1.8 (September 2024) is on the maker's site (rev 2 saw a v1.9 under an April 2026 address). No statement from the maker was seen. | digikey.com, findchips.com, pcxco.com, ovt.com; VERIFIED as "no notice found", which is not a promise |
| Warning signs? | The sibling OVM7692-RACA is listed obsolete; OVM7692-RAAA is a different size. Rev 2: RS said it would stop stocking the -RAAA. | as seen |
| Who stocks it in the US? | DigiKey only (884-1027-1-ND): 1,814 in stock on one of its pages and 2,497 on another, both undated. Arrow has a catalogue page with no stock or price. No Mouser, Newark, Avnet, Future or Rochester listing came up in two searches, one of them restricted to those sites. | digikey.com; VERIFIED as snapshots |
| What about the 6,282 pieces that rev 2 reported? | It is an aggregator's figure, with a 20-week lead time. It is close to a broker's stock shown on the same aggregator today (Vyrian, about 6,152), so it may not be DigiKey's. Plan on DigiKey's own 1,814 to 2,497. | findchips.com; not resolved |
| Brokers? | Quest Components 1,557 pieces (4.557 to 13.02 each, aggregator copy); Vyrian about 6,152; Win Source (China) 5,000 to 10,000; Microchip USA and PCX by quote. Brokers are not authorised sources and not a safe supply for an optical part. | aggregator copies |
| Lead time? | 14 weeks on DigiKey's page (manufacturer standard lead time); 20 weeks in the aggregator copy. Plan with 20 until DigiKey confirms. | digikey.com, findchips.com |
| Minimum order and package? | 1 piece on cut tape. A factory order is a full reel of 2,500: once the stock on hand runs out, the manufacturer's package and lead time apply. | digikey.com |
| Price? | USD 27.50 at 1 on cut tape; USD 6.25 each at 2,500 on reel. No price break in between was seen. These two figures were carried as unverified in rev 2; they are now seen on DigiKey's own page. | digikey.com; VERIFIED as seen |
| How many are needed? | 1000 markers need 2,000 cubes plus assembly losses: about one reel, and more than either DigiKey stock figure. | arithmetic |
| Drop-in alternative? | **None.** OVM7692-RAAA is 2.815 x 3.179 x 2.60 mm, so prism height, hoods and pads all change. The other OmniVision cubes at DigiKey are tiny medical cameras with other outputs (rev 2). | rev 2, not re-checked |
| Can an assembler solder it? | OmniVision describes it as a reflowable camera. The reflow limits, the lens protection and the pad map must come from the registered data sheet; the pad map in the netlist is a stand-in. | rev 2; PROVISIONAL |

### 9.2 Display: Sharp LS013B7DH03

The display is a "memory LCD": a reflective screen, like a calculator's but finer, that holds its picture on almost no power
and stays readable in sunlight. It is not a line of the board's BOM; it plugs into connector J1.

| Question | What was found | Source and status |
|---|---|---|
| Is it still made? | DigiKey: 'Part Status Active'. Octopart and Ciiva: 'Production' (Octopart's entry was last updated four months ago). Against that: a very old Mouser page says obsolete and not sold; the reseller West Florida Components says OBSOLETE; a broker marks the separate code LS013B7DH03-DU obsolete. No Sharp notice and no named successor were found in two independent searches. Sharp's own page was not seen. | VERIFIED as seen, with that conflict; "Active" rests on distributor fields only |
| US stock? | **Not established.** Undated copies of DigiKey's page seen today: 0 in stock (with 'Check Lead Time') on one; 206 on a category page; 5,233 and 5,674 on older captures; 10,863 in a 'similar parts' box; 27,098, 27,144 and 32,134 on others. The US page said 0 on 2026-11-11. Arrow: about 1,383, ships in 2 days (seen on its Mexico page). Future: 0, not stocked. | digikey.com, arrow.com, futureelectronics.com; snapshots that disagree |
| Lead time? | 28 weeks at DigiKey and at Future (20 weeks on one DigiKey page). | VERIFIED as seen |
| Price? | DigiKey, tray: USD 12.39 at 1, 9.60 at 10, 7.97 at 100, 7.74 at 500. On 2026-11-11 the same page gave 11.42, 8.82, 7.305 and 6.7715; which capture is the newer is not known. Future: 5.56 at 2,240 or more (6.54 on another page), 8.23 at 560, 13.46 at 2. | VERIFIED as seen |
| Pack sizes? | DigiKey's standard package is 1,120; Future's box and minimum is 2,240. | as seen |
| Thickness? | 0.741 mm in today's extracts; the design uses 0.746 mm. | to be settled from the Sharp drawing |
| Any change to the part? | Rev 2 reported a Sharp change notice for this display family (a new glass supplier; for some models a new glass thickness). Whether it touches this part was not confirmed then and was not looked at again. | rev 2; PROVISIONAL |
| Is Sharp leaving the business? | Rev 2: reports say Sharp will stop a large LCD plant in December 2026, and a distributor says its memory-display technology continues. Nothing names this part. Not looked at again. | rev 2 |
| Second source? | None that drops in. Sharp's LS013B7DH06 was looked at today: it is larger (26.82 x 31.3 mm against 26.6 x 30.3 mm) and Octopart lists it as obsolete. | octopart.com; PROVISIONAL |

### 9.3 Battery: 2 x 10 x 30 mm lithium-polymer cell with protection board

The protection board is a sliver of circuit on the end of the cell that cuts it off if it is over-charged, over-discharged
or shorted. The cell is not a line of the board's BOM; its leads are soldered to pads BT1 and BT2.

| Question | What was found | Source and status |
|---|---|---|
| Who sells it in the US? | PowerStream Technology, Utah: 'GM201030-PCB 43mAH 2x10x30mm $12.00 each'; without the board, 'GM201030 43mAH UN38.3 2x10x30mm $10.00 each'. The listing was seen today on two PowerStream pages. | powerstream.com; VERIFIED as a listing |
| How old is the listing? | One extract dates the page 27 September 2024; the other carried no date. A curved sister part, GM201030R, is 15.00 on a PowerStream page dated 5 November 2025, so the family was still on the site a year ago. | not resolved; price and availability are PROVISIONAL until PowerStream answers |
| Stock and lead time? | No count and no lead time. The listing has an 'Add to Cart' button; the site says 'the cells that have add to cart are in stock for sample quantities' and that it tries 'to keep 5 to 500 pieces in stock'. Also: 'prices are subject to change, please inquire for current prices'. | powerstream.com; a site-wide policy, not a figure for this part |
| Volume price? | Price tiers exist on the page, but their quantities were not readable. | **not found** |
| A trap in ordering? | Yes. The protection board 'is optional, and only included when requested'. Order in writing as GM201030-PCB. | powerstream.com |
| Safety papers and data? | 'UN38.3' is printed against the bare cell. The length with the board, the protection thresholds and any UL 1642 or IEC 62133 statement were not seen. The cell maker behind the GM number is not named. | **not found** |
| A second US source in the same size? | **Not found** in three searches. Nearest finds, none of which fits: AIN Battery AIN201030 (the maker's own site in China; 2.2 x 10.5 x 30.1 mm, 40 mAh, a curved cell, no protection board mentioned); a TinyCircuits 40 mAh protected cell (Ohio; dimensions not in the extract); a SparkFun 40 mAh cell (about 12.7 mm square); Akyga LP301020 (3 x 10 x 20 mm, Poland). | VERIFIED only as "none found in the searches made" |
| Could the page be read directly? | No. One attempt to open www.powerstream.com was refused: the host is outside this study's allowed network. | - |

---

## 10. Budgetary cost roll-up

> **This is an estimate for planning, not a costing.** 62 % of the 10-unit figure and 70 % of the 1000-unit figure rest on
> assumptions; only the remaining 38 % and 30 % come from a price that was seen, and a seen price is itself an undated
> extract. Everything marked "assumed" is this study's own guess, made so that the columns can be added up; replace each
> with a quote as it arrives.

The figures in this section are computed from `sourcing.csv` by the script printed in section 14. Each costed row of the csv
ends its notes with a line of the form `Roll-up: marker x8; q10 $0.620 [seen at 1]; q1000 $0.206 [seen at 3,000].` It says
which product the row belongs to, how many go into one unit, the price used at each quantity and, in square brackets, where
that price comes from. A price counts as **seen** only if its bracket starts with the word "seen".

### 10.1 Summary

| Cost block | At 10 units (USD per unit) | of which from a price seen | At 1000 units (USD per unit) | of which from a price seen |
|---|---|---|---|---|
| Electronic parts, display and cell | 119.35 | 102.78 | 45.80 | 39.17 |
| Optics, glass, vent, ball feet | 231.56 | 197.76 | 49.75 | 0.00 |
| Tapes, film and foam (material) | 7.50 | 3.35 | 0.22 | 0.00 |
| Adhesives and primer | 65.26 | 32.26 | 0.80 | 0.00 |
| Main circuit board | 90.00 | 0.00 | 7.00 | 0.00 |
| Circuit-board assembly | 200.00 | 0.00 | 12.00 | 0.00 |
| Base plate | 35.00 | 0.00 | 1.50 | 0.00 |
| 3D printing of the tub | 15.00 | 0.00 | 6.00 | 0.00 |
| 3D printing of the baffle-ring sets | 4.00 | 0.00 | 0.30 | 0.00 |
| Die cutting of the adhesive parts | 80.00 | 0.00 | 1.50 | 0.00 |
| **One marker, parts and outside services** | **847.67** | 336.15 | **124.87** | 39.17 |
| Cradle: electronic parts | 5.70 | 4.66 | 4.49 | 4.08 |
| Cradle: feet and screws | 1.04 | 0.44 | 0.56 | 0.44 |
| Cradle circuit board | 1.70 | 0.00 | 2.60 | 0.00 |
| Cradle: 3D printing of the cradle body | 40.00 | 0.00 | 12.00 | 0.00 |
| **One consumer cradle** | **48.44** | 5.10 | **19.65** | 4.53 |
| **Marker plus cradle** | **896.12** | 341.26 | **144.52** | 43.70 |
| Share that rests on assumptions | **62 %** | | **70 %** | |

Each figure is rounded on its own, so a column can differ from the sum of its rows by a cent. Revision 4 changed two priced
lines and nothing else: the Schottky diode (0.34 / 0.118, both seen) gave way to the ideal-diode switch U12 (0.29 seen at 1 /
0.132 seen at 500), and U11 is priced as the LP5907 (0.57 / 0.469, aggregator figures, not counted as seen) where it was the
MCP1700 (0.51 / 0.43, seen). The totals moved by one and five cents. These figures price ten
finished FR-4 markers and ten consumer cradles, and nothing else. The EVT programme that the other two plans describe is
larger; section 10.5 prices it.

**Which lines are seen prices and which are assumptions.** Of the 76 lines that carry a 10-unit price, 36 use a price that
was seen and 40 an assumption or an unverified figure. Of the 70 lines that carry a 1000-unit price, 25 are seen and 45 are
not. Section 10.4 gives the basis line by line. In short: the seen prices are the catalogue electronics, the prisms, the EVT
cover glass, the silicon nitride balls, the trial film, the cradle feet and five adhesive packs. The assumptions are
everything priced by quotation (bare board, board assembly, base plate, printing, die cutting, visor windows, production
glass, volume prisms), the vent, the cell at volume, four adhesive classes, and the small resistors and capacitors for which
no US-dollar price was seen at a small quantity.

One-time costs, kept out of the per-unit figures (the mould, not the cookies). Carried from rev 2; none was checked again:

| One-time item | Budget (USD) | Basis |
|---|---|---|
| Assembly fixtures and gauges for EVT (the list in `mechanical/README.md` section 2) | 8,000 to 15,000 | assumed range; no quote. Earlier research gave 1,500 to 5,000 for the pogo fixture and 3,000 to 8,000 for the calibration station, both unverified |
| FCC Part 15B emissions test | 1,500 to 5,000 | range seen on a low-reliability guide site and lab marketing pages; get quotes |
| Production tooling at 1000 units: die-cut tools, glass set-up, production leak tester, test fixtures | not estimated | earlier research gave 200 to 600 per die-cut tool, 500 to 2,000 glass set-up, 8,000 to 20,000 for a leak tester, all unverified |

What ten bare units would cost to place, in round figures (the whole EVT programme is in section 10.5):

| Step | USD |
|---|---|
| 10 markers and 10 cradles at the per-unit figure above | 8,961 |
| Spares and minimum packs: 15 % on the catalogue parts (assumed) | 548 |
| Fixtures and gauges | 8,000 to 15,000 |
| FCC test | 1,500 to 5,000 |
| **Total outlay for ten bare units** | **about 19,000 to 29,500** (rounded) |

Amortised separately, the fixtures add USD 800 to 1,500 to each of 10 units, or USD 8 to 15 to each of 1000 units. For 1000
units the parts and outside services come to about USD 145,000 for markers with cradles (rounded), before final-assembly
labour, tooling and scrap.

### 10.2 What moves the answer most

| If this changes... | ...the figure moves like this |
|---|---|
| Volume price of the prism (assumed USD 15 each; no source) | at USD 5 each the 1000-unit marker is about USD 105; at Edmund's published 26-to-49 price of USD 78.50 each it is about USD 252 |
| Board assembly lot charge at 10 units (assumed USD 2,000) | each USD 500 moves the 10-unit marker by USD 50 |
| Bare-board lot charge at 10 units (assumed USD 900) | each USD 300 moves the 10-unit marker by USD 30 |
| Camera price at 10 units (USD 27.50 each, the single-piece price; no break below 2,500 was seen) | each USD 5 moves the marker by USD 10 |
| Ball material (silicon nitride at USD 2.37 each, seen; no US price was found for a 316 stainless ball) | if a stainless ball were quoted at USD 0.10, the marker would fall by USD 6.81 at 10 units and USD 6.45 at 1000 |
| Microcontroller price (USD 12.16 at 1 and 7.52 at 500 on DigiKey's US page; 4.83 at Future, which has none) | moves the marker one for one: up to USD 7 lower at 10 units |
| Cell price at 1000 (assumed USD 5) | moves the marker one for one |

### 10.3 Assumptions

1. **Quantities** now come from the two real bills of materials. Parts marked "not fitted" are not costed.
2. **"At 10" prices** use the published 10-piece price where one was seen; otherwise the single-piece price; otherwise the
   price at the quantity named in the bracket; otherwise an assumption. For the resistors and small capacitors for which no
   US-dollar price was seen at a small quantity, USD 0.10 each is assumed, the single-piece price seen on sibling values.
   That overstates them; together they come to about USD 4 per marker.
3. **"At 1000" prices** use the published 1000-piece price where seen; otherwise the nearest price break that was seen (the
   bracket says which); otherwise an assumption.
4. **Lot charges at 10 units** (bare boards USD 900 for about 20; assembly USD 2,000 for about 12; base plates USD 350 for
   about 30; die cutting USD 800 for about 25 sets) are assumed and divided by 10. No published price for this class of work
   was seen.
5. **Adhesives at 10 units** are costed as one small pack of each class, divided by 10. Five of the nine packs now use a
   price that was seen (ball potting, window adhesive, rim sealant, prism adhesive, thermal adhesive); the primer uses a
   seen price for an assumed five ampules. Most of each pack is left over.
6. **Printing** is assumed at USD 15 per tub with dye and vapor smoothing, USD 40 per cradle body, USD 4 of baffle rings per
   marker at 10 units; USD 6, 12 and 0.30 at 1000. Bureau minimum order charges are not included.
7. **Three lines are priced at their replacement part**, because the part in the BOM cannot or should not be bought: the 1
   uF and 2.2 uF capacitors and the cradle fuse.
8. **The ball feet are priced as silicon nitride** at both quantities, because that is the only US price seen.
9. **What does not count as a price seen:** the cell (a listing whose date is in doubt), the charger at 1000 (a figure
   handed to this study, not seen by it), the cradle fuse (an aggregator figure for a slightly different search string), and
   every "assumed".
10. **Not included anywhere:** final-assembly labour (19 hand steps per marker), test time, yield loss and scrap, packaging,
    the USB cable and charger, freight, sales tax, tariffs (three distributor pages carried tariff notices), engineering
    time, and the test equipment that `VALIDATION_PLAN.md` asks for. The per-unit figures also leave out the alternative
    PA12 base-plate build and the cradles with seven pins; section 10.5 adds them.
11. **Currency.** Where only a euro, pound or Canadian-dollar price was seen, it is not used: the line is marked assumed.
12. The 10-unit column uses the Edmund catalogue prism, the watch-crystal cover glass and the trial film; the 1000-unit
    column uses a quoted volume prism and a custom strengthened cover glass, and no film. That is why those lines show a
    cost in only one column.

### 10.4 Line-by-line basis

"seen" means the unit price came from a search result; the words after it say at what quantity, or on what date if not
2026-11-13. Everything else did not come from a price that was seen.

| Line | Per | Qty | Each at 10 (USD) | Basis | Each at 1000 (USD) | Basis |
|---|---|---|---|---|---|---|
| main-01: Capacitor 100 nF 16 V X7R 0402 (16 per marker) | marker | 16 | 0.100 | seen at 1 | 0.00805 | seen |
| main-02: Capacitor 4.7 uF 6.3 V X5R 0402 (2 per marker) | marker | 2 | 0.120 | seen at 1 | 0.029 | seen at 500 |
| main-03: Capacitor 1 uF 10 V X5R 0402 (8 per marker) | marker | 8 | 0.100 | seen at 1: Newark | 0.010 | assumed |
| main-04: Capacitor 10 nF 50 V X7R 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.006 | assumed |
| main-05: Capacitor 6.8 pF 50 V C0G 0402, +-0.25 pF (2 per marker) | marker | 2 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.006 | assumed |
| main-06: Capacitor 2.2 uF 10 V X5R 0402 (4 per marker) | marker | 4 | 0.110 | seen, quantity not stated: DigiKey | 0.015 | assumed |
| main-07: Capacitor 10 pF 50 V C0G 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.006 | assumed |
| main-08: Red LED, 0402 (8 per marker) | marker | 8 | 0.120 | seen at 100, aggregator copy | 0.055 | seen, quantity not stated, aggregator copy |
| main-09: Near-infrared LED, 0402 (8 per marker) | marker | 8 | 0.620 | seen at 1 | 0.206 | seen at 3,000 |
| main-10: Display connector, 10-way 0.5 mm, top contact | marker | 1 | 1.22 | seen at 1 | 0.680 | seen at 2,000 |
| main-11: Photodiode (grain reader) | marker | 1 | 1.86 | seen at 1 | 1.11 | seen, quantity not stated |
| main-12: Small N-channel MOSFET, SOT-23 | marker | 1 | 0.340 | seen at 1 | 0.073 | seen on 2026-11-11 |
| main-13: Resistor 10 ohm 1 % 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-14: Resistor 10 kohm 1 % 0402 (2 per marker) | marker | 2 | 0.100 | seen at 1 | 0.006 | assumed: only a Canadian-dollar price was seen |
| main-15: Resistor 100 kohm 1 % 0402 (11 per marker) | marker | 11 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.0013 | seen at 10,000 |
| main-16: Resistor 1 kohm 1 % 0402 (2 per marker) | marker | 2 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-17: Resistor 2.2 kohm 1 % 0402 (3 per marker) | marker | 3 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-18: Resistor 33 ohm 1 % 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-19: Resistor 6.81 kohm 1 % 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-20: Resistor 1 Mohm 1 % 0402 (2 per marker) | marker | 2 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-21: Resistor 68 ohm 1 % 0402 (5 per marker) | marker | 5 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-22: Resistor 470 kohm 1 % 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-23: Resistor 150 kohm 1 % 0402 (1 per marker) | marker | 1 | 0.100 | assumed: the single-piece price seen on a sibling value | 0.004 | assumed |
| main-24: Resistor array 4 x 220 ohm, 0804 (6 per marker) | marker | 6 | 0.100 | assumed | 0.031 | seen on 2026-11-11, quantity not stated |
| main-25: Temperature sensor: NTC thermistor 10 kohm 1 %, 0402 (2 per marker) | marker | 2 | 0.100 | assumed | 0.037 | seen at 10,000 |
| main-26: Microcontroller, LQFP-64 | marker | 1 | 12.16 | seen at 1 | 7.52 | seen at 500 |
| main-27: Camera cube (2 per marker) | marker | 2 | 27.50 | seen at 1 | 6.25 | seen at 2,500 |
| main-28: Tilt and motion sensor (IMU), LGA-14 | marker | 1 | 5.75 | seen at 1 | 3.71 | seen at 5,000 |
| main-29: Flash memory 64 Mbit, 8-WSON (tray code) | marker | 1 | 3.61 | seen at 1, conflicting: Mouser cut tape of the reel code | 1.66 | seen, quantity not stated: Arrow US, reel code |
| main-30: Always-on 2.8 V regulator, SOT-23 | marker | 1 | 0.510 | seen at 1 | 0.390 | seen at 3,000 |
| main-31: Switchable 2.8 V regulator for the cameras, SOT-23-5 | marker | 1 | 0.402 | seen on 2026-11-11 | 0.290 | seen |
| main-32: Battery charger chip, DSBGA-6 | marker | 1 | 1.61 | seen at 1 | 0.913 | reported, unverified |
| main-33: USB static-discharge protection, SOT-23-6 | marker | 1 | 0.243 | seen | 0.114 | seen |
| main-34: 3.3 V regulator with enable for the USB supply pin, SOT-23-5 | marker | 1 | 0.570 | aggregator figure at 1, unverified | 0.469 | aggregator figure, unverified |
| main-35: Ideal-diode switch, SC-70-6 | marker | 1 | 0.290 | seen at 1 | 0.132 | seen at 500 |
| main-36: 32.768 kHz crystal, 3.2 x 1.5 mm | marker | 1 | 0.990 | seen at 1 | 0.706 | seen at 5,000 |
| Display (memory LCD, 1.28 inch, 128 x 128) | marker | 1 | 9.60 | seen | 7.74 | seen at 500 |
| Lithium-polymer cell with protection board, 2 x 10 x 30 mm, 43 mAh | marker | 1 | 12.00 | listed, unconfirmed | 5.00 | assumed |
| cradle-01: Capacitor 100 nF 16 V X7R 0402 (1 per cradle) | cradle | 1 | 0.100 | seen at 1 | 0.00805 | seen |
| cradle-02: Resettable fuse on the 5 V line, 0603 (1 per cradle) | cradle | 1 | 0.840 | aggregator figure, unverified | 0.400 | aggregator figure at 4,000, unverified |
| cradle-03: USB-C socket (1 per cradle) | cradle | 1 | 0.917 | seen on 2026-11-11 | 0.440 | seen at 2,400, aggregator copy |
| cradle-04: Resistor 5.1 kohm 1 % 0402 (2 per cradle) | cradle | 2 | 0.100 | assumed | 0.004 | assumed |
| cradle-05: Spring pins (4 fitted in the consumer cradle) | cradle | 4 | 0.850 | seen at 1 on 2026-11-11 | 0.880 | seen on 2026-11-11 |
| cradle-06: USB static-discharge protection, SOT-23-6 (1 per cradle) | cradle | 1 | 0.243 | seen | 0.114 | seen |
| Fold prism, 2.0 mm (2 per marker) | marker | 2 | 94.50 | seen on 2026-11-11 | - | not used: see the production prism line |
| Fold prism, production volume source | marker | 2 | - | not used: see the EVT prism line | 15.00 | assumed, no source |
| Ball feet, 1.0 mm (3 per marker) | marker | 3 | 2.37 | seen at 1 | 2.25 | assumed: 5 % under the single-piece price, as on sister sizes |
| Cover glass, EVT (flat mineral-glass watch crystal, 28.0 x 1.0 mm) | marker | 1 | 1.65 | seen on 2026-11-11 | - | not used: see the production cover-glass line |
| Cover glass, production (chemically strengthened, printed black border) | marker | 1 | - | not used: see the EVT cover-glass line | 8.00 | assumed |
| Visor windows, 0.40 mm borosilicate, cut 5.0 x 3.25 mm (2 per marker) | marker | 2 | 15.00 | assumed | 1.50 | assumed |
| Pressure-equalisation vent, adhesive, 5.0 mm | marker | 1 | 3.80 | assumed: converted from a UK price | 2.00 | assumed |
| Rubber feet for the cradle (4 per cradle) | cradle | 4 | 0.111 | seen at 144 | 0.111 | seen at 144 |
| Screws for the cradle board, M2 x 4 thread-forming for plastic (4 per cradle) | cradle | 4 | 0.150 | assumed | 0.030 | assumed |
| Adhesive sheet material, circuit board to base plate (FR-4 build) | marker | 1 | 0.500 | assumed | - | in the die-cutting line |
| Transfer tape, cover-glass ring (also the sheet of the PA12 build) | marker | 1 | 0.200 | assumed | - | in the die-cutting line |
| Adhesive frame for the display, 0.15 mm foam type | marker | 1 | 0.300 | assumed | - | in the die-cutting line |
| Opaque black double-coated tape for the baffle annulus (E16: 0.10 to 0.145 mm) | marker | 1 | 0.100 | assumed | - | in the die-cutting line |
| Cell fixing adhesive (E22: 0.06 mm or less) | marker | 1 | 0.050 | assumed | 0.020 | assumed |
| Foam pad under the display, 0.3 mm | marker | 1 | 1.00 | assumed | 0.200 | assumed |
| Quarter-wave film for the sunglasses trial (EVT only; cut to dia 23.4 mm) | marker | 1 | 3.35 | seen: one sheet at 33.50 over 10 units | - | not used: a trial; if adopted, about 2 to 4 per marker |
| Optically clear adhesive for the quarter-wave film (EVT trial) | marker | 1 | 2.00 | assumed | - | not used: a trial |
| Perimeter seal adhesive (class) | marker | 1 | 8.00 | assumed: one pack over 10 units | 0.150 | assumed |
| Ball-foot potting epoxy (class) | marker | 1 | 5.26 | seen: one 50 mL cartridge of DP460 at 52.62 over 10 units | 0.050 | assumed |
| Visor-window adhesive, thixotropic light-cure (class) | marker | 1 | 11.28 | seen: one 30 mL syringe of 6-621-GEL at 112.77 over 10 units | 0.100 | assumed |
| Clear optical potting for the grain opening (class) | marker | 1 | 15.00 | assumed: one pack over 10 units | 0.200 | assumed |
| Hood gasket bead, black, soft, silicone-free (class) | marker | 1 | 10.00 | assumed: one pack over 10 units | 0.100 | assumed |
| Cover-glass rim sealant, black, wicking grade (class) | marker | 1 | 7.15 | seen: one 450 mL kit of 832FX at 71.46 over 10 units | 0.050 | assumed |
| Prism bonding adhesive, UV-cure (class) | marker | 1 | 3.80 | seen: one 1 oz bottle of NOA 61 at 38.00 over 10 units | 0.050 | assumed |
| Primer or plasma treatment for the nylon bonding faces (class) | marker | 1 | 1.28 | seen price, assumed quantity: five ampules of Primer 94 at 2.56 over 10 units | 0.050 | assumed |
| Thermal adhesive for the two temperature sensors (class) | marker | 1 | 3.49 | seen: one 25 mL syringe of 8329TFF at 34.89 over 10 units | 0.050 | assumed |
| Main circuit board, bare (4 layers, 0.8 mm, ENIG, 0.10 / 0.10 mm in the fine areas, through vias) | marker | 1 | 90.00 | assumed: 900 per lot of about 20, over 10 units | 7.00 | assumed, including selective hard gold |
| Circuit-board assembly (both sides, two camera cubes, LGA sensor, 64-pin processor, 0402 parts) | marker | 1 | 200.00 | assumed: 2,000 per lot of about 12, over 10 units | 12.00 | assumed |
| Base plate, routed 0.80 mm FR-4, no copper, matte black mask (drawing GL1-011) | marker | 1 | 35.00 | assumed: 350 per lot of about 30, over 10 units | 1.50 | assumed |
| Cradle circuit board (2 layers, 1.0 mm, 30 x 22 mm) and its assembly | cradle | 1 | 1.70 | assumed, hand-soldered | 2.60 | assumed: board 0.60 and assembly 2.00 |
| 3D printing of the tub (HP Multi Jet Fusion PA12, dyed black, vapor smoothed) | marker | 1 | 15.00 | assumed | 6.00 | assumed |
| 3D printing of the baffle-ring sets (MJF PA12, dyed black, not smoothed) | marker | 1 | 4.00 | assumed | 0.300 | assumed |
| 3D printing of the cradle body (MJF PA12, not smoothed, not tumbled) | cradle | 1 | 40.00 | assumed | 12.00 | assumed |
| Die cutting of the adhesive parts (patterns GL1-030, -031, -032, -033, -034) | marker | 1 | 80.00 | assumed: 800 per lot, over 10 units | 1.50 | assumed, all cut parts including the tape |

### 10.5 The whole EVT programme: what the ten-unit figure leaves out

The figures above are like costing a recipe per plate. The kitchen also has to cook the trial portions. The other two plans
ask for much more hardware than ten finished units (this table is carried from rev 2; the plans were not re-read):

| What | How many | Where it comes from |
|---|---|---|
| Build kits (parts for a complete marker) | 15, to finish 10 | `MANUFACTURING_PLAN.md` 2.1 |
| Units on the printed PA12 base plate | 4 of the 10 (so 6 of the 15 kits) | `MANUFACTURING_PLAN.md` 2.3 |
| Spare assembled boards for the tests before sealing | 8 to 10 (10 used here) | `VALIDATION_PLAN.md` 4.1 |
| Marker shells without working electronics, for destructive tests | 20: 10 with each base plate | `VALIDATION_PLAN.md` 4.1 (PROPOSED there) |
| Dummy markers for the first seating test | 2 | `VALIDATION_PLAN.md` 4.1 |
| Cradles | 12, of which 4 with seven pins | `VALIDATION_PLAN.md` 4.1, tests M1 and M2 |
| Loose cells | 8 | `VALIDATION_PLAN.md` 4.1 |

That makes about 25 assembled boards, about 45 bare boards, about 40 tubs, about 21 FR-4 and 16 PA12 base plates, and about
35 sets of cut tapes. Neither plan is a parts list, so the counts are **PROPOSED**. A rough budget for it, built from the
unit figures of section 10.4; every lot charge is assumed:

| Item | Quantity and unit figure (USD) | Budget (USD) | Basis |
|---|---|---|---|
| Electronic parts for 25 assembled boards (15 builds and 10 spare boards), without cell and display | 25 x 97.75 | 2,444 | as in 10.4 (mixed) |
| Displays (15 builds and 2 shells with displays for the swollen-cell test) | 17 x 9.60 | 163 | seen |
| Cells (15 builds and 8 loose cells) | 23 x 12.00 | 276 | listed, unconfirmed |
| Prisms (2 per build; 30 pieces fall in Edmund's 26 to 49 price step) | 30 x 78.50 | 2,355 | seen on 2026-11-11 |
| Cover glass, visor windows, vents and ball feet for 15 builds and 20 shells (40 / 80 / 40 / 120 pieces) | 40 x 1.65; 80 x 15.00; 40 x 3.80; 120 x 2.37 | 1,702 | glass and balls seen; windows and vents assumed |
| Tape, film and foam material for 35 | 35 x 7.50 | 262 | assumed, except the trial film |
| Adhesives and primer: two small packs of each class (shells and coupons use them too) | 2 x 652.60 | 1,305 | five pack prices seen, four assumed |
| Bare main boards, one lot of about 45 | lot | 1,800 | assumed (USD 900 for about 20, scaled) |
| Board assembly, 25 boards | lot | 3,600 | assumed (USD 2,000 for about 12, scaled) |
| FR-4 base plates, about 21 needed (GL1-011) | lot of about 30 | 350 | assumed |
| Printed PA12 base plates, about 16 needed (GL1-012) | 20 x 8.00 | 160 | assumed |
| Printed tubs (15 builds, 20 shells, 2 dummies, 3 spare) | 40 x 15.00 | 600 | assumed |
| Baffle-ring sets for the 19 FR-4 builds and shells | 19 x 4.00 | 76 | assumed |
| Die cutting, about 40 sets, five patterns | lot | 1,300 | assumed (USD 800 for about 25 sets of four patterns, scaled) |
| Cradles: 12, of which 4 with seven pins for the creep test | 12 x 48.44 + 12 pins x 0.85 | 592 | as in 10.4 (mostly assumed) |
| **EVT programme, parts and outside services** | | **about 17,000** | |

| Step | USD |
|---|---|
| Ten bare units with 15 % spares (section 10.1), for comparison | about 9,500 |
| EVT programme, parts and outside services | about 17,000 |
| Fixtures and gauges | 8,000 to 15,000 |
| **Outlay for the EVT programme, before test equipment and labour** | **about 25,000 to 32,000** (rounded) |

Not in this figure: the test equipment and lab time of `VALIDATION_PLAN.md`, the formal FCC test (it belongs to a later
build), labour, freight, tariffs and tax. About 36 % of the EVT figure rests on a price seen (mostly the electronics, the
prisms and the balls); the rest is assumed. Treat it as a size, not a quote.

---

## 11. What could not be verified

1. **Any live stock figure or live price.** Every number is an undated extract; four attempts to open a supplier page were
   refused.
2. **US-dollar prices at exactly 10 and at exactly 1000** for most lines. A price at exactly 10 was seen today for the
   display, the static-protection chip, the Samsung 100 nF alternate, the Inolux LED, the trial film (per sheet), the prism
   adhesive and the two primers; at exactly 1000 for the 100 nF capacitor, the camera regulator, the
   static-protection chip and the Inolux LED. Elsewhere the nearest break is used and named.
3. **Camera cube:** any statement from OmniVision, a price between 1 and 2,500 pieces, the pad map, the reflow limits, and
   whose stock the figure of 6,282 is.
4. **Display:** the stock on DigiKey's live page, Sharp's own status, the change notice reported in rev 2, the thickness.
5. **Cell:** stock, lead time, any price above quantity 1, the date of the listing, the cell maker, the protection data and
   the certificates.
6. **U11, the part that amendment E26 names** (LP5907MFX-3.3/NOPB, on the BOM since revision E): DigiKey's US page, a stock figure on which its regional pages
   agree (they ran from "out of stock" to about 108,000), its part status, and a price that is not an aggregator's copy.
7. **Mill-Max spring pin:** tail length, barrel diameter and plunger diameter; the drawing could not be opened.
8. **McMaster-Carr:** a part number, the size and the price of the 4 mm screw that the revision E model calls for (E36); that
   screw 96817A207 (5 mm) is M2; the full number of the 2.8 mm bumper; and, on the live page,
   that the 316 stainless line really has no 1 mm ball.
9. **Murata's own word** on the 100 nF capacitor's status; the own pages of GRM155R61C105KA12D and GRT155R61A225KE01D; the
   second DigiKey entry for GRM155R61A225KE01D, and that this number is Murata's successor to GRM155R61A225KE95D (an
   inference from the 20 % sibling).
10. **Infrared LED SFH 4053B:** its data sheet (wavelength, package, pads, polarity) and whether it is being discontinued.
11. **Display connector:** that the top-contact FH12A fits the FH12 land pattern; its 2.0 mm height.
12. **Alternates:** the ten Panasonic resistor numbers built from memory; Bourns CAY10-221J4LF; Samsung CL05C6R8CB5NNNC
    (searched, **not found**); whether the Yageo array and the TDK thermistor are true drop-ins.
13. **Capacitance under working voltage** of every 1 uF, 2.2 uF and 4.7 uF capacitor: the figures in A3 are from memory; no
    maker's curve was seen.
14. **Ball feet:** a US seller of a 1.0 mm 316 grade 100 ball; Boca's price a second time; VXB's true diameter; the spread
    of diameter inside one lot (5 um from memory of the standard, 2.5 um in one secondary table).
15. **Vent:** a US price or stock figure for Gore VE80205, and its water-entry pressure; whether Porex sells a 5.0 x 2.0 mm
    disc.
16. **Glass:** today's stocked thicknesses at Abrisa (its lists are undated or old), any strength figure, any price; minimum
    part size for the visor windows.
17. **Tapes, film, foam:** light transmission of 3M 9495B in any direction; a US seller of tesa 61361; the roll width of the
    467MP listing; the Edmund stock number and true thickness of the quarter-wave film; any optically clear adhesive (not
    searched); the price, stock and compression force of the PORON item.
18. **Adhesives:** the hardness and cure time of MG 832FX; the resistivity and cure time of MG 8329TFF; the mixed viscosity
    of Master Bond EP30-2; the viscosity of 3M DP460; fluorescence of any clear potting; opacity of any hood gasket; a
    primer recommendation for nylon; adhesion of everything to vapor-smoothed PA12 and to solder mask.
19. **Not checked a second time** (the second check ran out of searches): the microcontroller's price, the tilt sensor's
    stock, the flash memory's tray and reel codes, the thermistor and its TDK alternate, the resistor-array alternate, the
    cradle feet, the USB-C socket, the cell.
20. **Everything dated 2026-11-11:** the prisms, the EVT cover glass, tapes 93020LE and 9472LE, the perimeter-seal and
    hood-gasket candidates, Loctite E-30CL, a US listing for EPO-TEK 301 and 301-2, and every custom part and outside
    service of section 8, with all that rev 2 worded "reported in review". For the services, no company was asked whether it
    will take this job.
21. **Not searched at all:** the fallback display connector that amendment E24 names (a 1.0 mm high back-flip connector of
    the Hirose FH34SRJ-10S-0.5SH class); a second maker's part for the E25 switch; an optically clear adhesive for the film;
    plasma treatment; machined gauges; selective hard gold; black Nitto tapes; a 3M urethane foam; a vent sold under the
    name Voxx; screws at DigiKey.
22. **Country of manufacture** for almost every line.

---

## 12. Design actions

These are for the design owners. Nothing under `design/`, `mechanical/`, `firmware/` or `electrical/` was edited by this
study. **Section 12.0 gives the state of each action at design revision E-EVT1**; the table of section 12.1 is kept as it
was written on 2026-11-13 (only its BOM line numbers follow the revision E parts list), so its "what is wrong" cells
describe revision D. Section 12.1 lists the 35 actions that came out of this revision: every part whose number was wrong, obsolete,
mismatched or single-sourced, with the proposed fix. Section 12.2 carries the rev 2 items that are still open, 12.3 lists
the rev 2 items that the amendments have closed, and 12.4 suggests an order in which to buy.

### 12.0 State of the actions at design revision E-EVT1 (2026-11-18)

Read from the design files and the two status BOMs (`electrical/gl1_main/out/assembly/gl1_main-bom-status.csv`,
`electrical/gl1_cradle/out/assembly/gl1_cradle-bom-status.csv`), not from a new search. "Applied" means the design files
carry the change; it does not mean a board was built or a data sheet was read.

| Action | State at revision E |
|---|---|
| A1 | applied: line 3 is Samsung CL05A105KP5NNNC |
| A2 | applied: line 6 is Murata GRM155R61A225KE01D; that it succeeds the KE95D code is still an inference, and its second DigiKey entry is still unread |
| A3 | open: no DC-bias curve was read; a larger case would be a footprint change |
| A4 | applied as a candidate: the status BOMs name Samsung CL05B104KO5NNNC beside the 100 nF lines; not an approved alternate (A18) |
| A5 | applied: cradle F1 is Littelfuse 0603L035YR. Open for the specification owner: its 0.75 A trip against amendment E6's "about 0.5 A"; the 6 V rating; the 1206 fallback was not adopted |
| A6 | applied in the board: tail 0.635 mm, finished hole 0.80 mm. Open: the tail length (1.34 mm in `master_params.yaml`, PROVISIONAL; amendment E36 made the board 1.0 mm so that this tail comes through by 0.34 mm), and the mechanical model still draws a 0.76 mm tail in a 0.90 mm hole; the Mill-Max drawing is still unread |
| A7 | applied: U12 is TI LM66100DCKR (line 35, DigiKey 296-53541-1-ND); the Schottky diode D17 is gone. Its pin table and wiring stay PROVISIONAL until the data sheet is read |
| A8 | applied: U11 is TI LP5907MFX-3.3/NOPB (line 34). Open: the order code, which waits for the live US page |
| A9 | applied: SFH 4053B kept, Inolux IN-S42CTQIR named as the candidate; data sheet unread |
| A10, A16 | not design-file changes; open with the buyer |
| A11, A12 | open: the display and the cell are on no purchasing list (the main board's assembly README names them as off-board items) |
| A13 | applied: U4 from Newark (62AK1744) at 5.75 |
| A14 | open: tray or reel code of the flash memory, with the assembler |
| A15 | open: the FH12A on the FH12 land pattern and its 2.0 mm height are unchecked against Hirose's drawing |
| A17 | applied for the order codes and prices named, except that the Schottky diode's price no longer applies; cradle R1 / R2 and C1 codes entered |
| A18 | partly: the status BOMs have an alternates column, headed as candidates. No alternate is approved; the ten ERJ values and ERJ-2RKF5101X are still PROVISIONAL |
| A20 | decided in the model: M2 x 4 in pilot holes dia 1.6 x 3.2 (amendment E36, cradle board 1.0 mm). Open: no part number for a 4 mm screw has been seen (section 5) |
| A25 | closed by amendment E22: `battery.fixing_adhesive_max` is 0.06 |
| A19, A21 to A24, A26 to A35 | not re-read for revision 4: as written in 12.1 |

### 12.1 Actions from revision 3 (2026-11-13)

| # | File and place | What is wrong | Proposed fix |
|---|---|---|---|
| A1 | Main board BOM line 3 (C7 C16 C19 C20 C21 C24 C25 C32, 1 uF 10 V X5R 0402) | Murata GRM155R61A105KE15D is OBSOLETE (DigiKey: 'Obsolete and no longer manufactured'; Arrow: last-time buy / obsolete; Findchips: 'Obsolete'). No distributor stock was seen. | Change the part number to Samsung CL05A105KP5NNNC (same value, voltage, dielectric, tolerance and size; Active; DigiKey regional pages 3.95 to 4.48 million in stock; Avnet Americas 2,230,000). Do not move to GRM155R61C105KE01D, GRM155R61A105KE15J or GRM155R61A105ME15D (all obsolete at DigiKey), nor to GRM155R61A105KE01D or GRT155R61A105KE01D (no stocked listing found). Murata GRM155R61C105KA12D (16 V) may become the second source only after its own DigiKey page and Murata's status have been read (PROVISIONAL). |
| A2 | Main board BOM line 6 (C22 C23 C26 C27, 2.2 uF 10 V X5R 0402) | Murata GRM155R61A225KE95D is being discontinued and no US stock was seen (DigiKey: 'no longer available at DigiKey'; Arrow: 'LTB-Unconfirmed'; RS: being discontinued by the manufacturer). It is not confirmed obsolete: one weaker source (Ciiva) still says 'Volume Production'. | Change the part number to Murata GRM155R61A225KE01D and approve Samsung CL05A225KP5NSNC (Mouser 29,841 in stock) as second source. That KE01D succeeds KE95D is inferred, not seen (DigiKey names GRM155R61A225ME01D as the substitute for the obsolete 20 % sibling GRM155R61A225ME95D): confirm it. The replacement was not seen in stock under its own code: read both of its DigiKey entries (10695166 showed out of stock with a 17-week lead; 13544360 was not read); Mouser showed 47,312 under the large-reel code GRM155R61A225KE01J. Use Murata GRT155R61A225KE01D only after its own page has been read (PROVISIONAL). |
| A3 | Main board: every 1 uF, 2.2 uF and 4.7 uF 0402 capacitor (C5; C7 C21 C25 C32; C20 C24; C22 C23 C26 C27) | A small high-value ceramic capacitor keeps only part of its capacitance at its working voltage. From memory, not seen today: about 0.6 uF of the 1 uF parts is left on the cell rail at 4.2 V (C20, C24) and about 0.8 uF at 2.8 V; about 0.9 to 1 uF of the 2.2 uF parts at 5 V (C22, C26) and about half at 4.2 V (C27); about 2.3 to 3 uF of the 4.7 uF part at 2.8 V (C5). | Because the 1 uF and 2.2 uF part numbers change anyway (A1, A2), read the DC-bias curves of the replacement parts (Murata SimSurfing or Samsung's equivalent) and check them against the minimum effective capacitance that the regulators U7, U8 and U11 and the charger U9 need. Where a position is short, go up one value or one case size. |
| A4 | Main board BOM line 1 and cradle BOM line 1 (100 nF 16 V X7R 0402, 17 placements) | Murata GRM155R71C104KA88D has a conflicting life-cycle flag: 'not recommended for new designs' at Octopart, IBS and LCSC; 'Active' at Arrow and Future. Murata's own page was not seen. Stock is deep. | Add Samsung CL05B104KO5NNNC (same value, voltage, dielectric and size) as an approved alternate on both BOMs, and confirm the Murata part's status on Murata's site before a production buy. Read the live DigiKey page for the Samsung part before naming a distributor: two snapshots of the same order code disagreed today (out of stock against 3,534,602). |
| A5 | Cradle BOM line 2 (F1); PTC table in electrical/gl1_cradle/gl1_cradle_design.py; wording of amendment E6 | The netlist's fuse, Bourns MF-FSMF020X-2 (0603, 9 V, hold 0.2 A, trip 0.5 A), has a resistance after a trip of 3.5 ohm maximum. Amendment E25 allows 1.5 ohm at most. No 0603 part with a 0.2 A hold current that was seen meets 1.5 ohm. | Change F1 to Littelfuse 0603L035YR (same 0603 pads; 6 V; hold 0.35 A; trip 0.75 A; 1 ohm maximum after a trip; Active; DigiKey US page 17,643 in stock). Second source on the same pads: Bourns MF-FSMF035X-2 (1.4 ohm maximum, so only 0.1 ohm inside the limit; Master Electronics 24,430 in stock, minimum order 1,000). Update the PTC table and change E6's 'trip about 0.5 A' to 0.75 A. The designers must accept two things: on a source limited to exactly 0.5 A a hard short is ended by the source's own limiter, not by the fuse; and a 6 V rating has no margin over a 5.5 V bus. If margin is wanted, the fallback is Bourns MF-NSMF050-2 (1206, 13.2 V, hold 0.5 A, trip 1 A, 0.7 ohm maximum), which needs a 1206 footprint. |
| A6 | Cradle BOM lines 5 and 7 (SP1 to SP7); MILLMAX_0914 in electrical/gl1_cradle/gl1_cradle_design.py; the seven 0.90 mm drills of the cradle fabrication set; mechanical/README.md part list item 20 | The footprint is wrong for Mill-Max 0914-0-15-20-77-14-11-0. Its solder tail is 0.025 in (0.635 mm) and Mill-Max's minimum mounting hole is 0.029 in (0.737 mm); the netlist assumes a 0.76 mm tail in a 0.90 mm hole. The tail also looks shorter than the board: 8.3 mm overall less 6.96 mm above the board is about 1.34 mm against a 1.6 mm board (a subtraction of two extracts, not a reading). It is a single-maker part. | Set tail_dia to 0.635 mm, size the hole from Mill-Max's 0.737 mm minimum and the pad to suit, and regenerate the drill file before the cradle board is ordered. Read the Mill-Max drawing for tail length, barrel diameter and plunger diameter (www.mill-max.com or assets.rs-online.com has to be allowed in the session's network settings, or the PDF supplied). If the short tail is confirmed, choose one: accept a solder joint inside the plated hole, use a thinner board, or change to the long-tail 0914-1-15-20-77-14-11-0 (11.35 mm overall; a DigiKey listing exists; nothing else read) and check the room under the board. |
| A7 | Amendment E25 against the main board netlist (D17 of revision D, its BOM line 10; since revision E: U12, main BOM line 35) | E25 replaces the Schottky diode D17 (B0530WS-7-F) with the ideal-diode switch TI LM66100DCKR, but the netlist and BOM still carry the diode. The new part is no longer a sourcing question: DigiKey lists it (296-53541-1-ND, SC-70-6) with 53,573 in stock on its US page, at 0.29 USD for one on a DigiKey page priced in USD, and it is Active at TI, DigiKey and Arrow. | Work E25 into the netlist and the BOM: read the TI data sheet for the wiring (E25 marks it PROVISIONAL), replace the SOD-323 footprint with the SC-70-6 one, and enter the order code. Read the live DigiKey page before ordering (regional pages ran from 13,653 to 66,618, and one Canada punch-out page showed 0). Do not buy B0530WS-7-F for production: its DigiKey stock picture conflicts (403, out of stock, 35,014 and 108,417 on four extracts) and its lead time was 40 weeks on 2026-11-11. |
| A8 | Amendment E26 against the main board netlist (U11; main BOM line 34, line 35 in revision D) | E26 replaces U11 (MCP1700T-3302E/TT) with TI LP5907MFX-3.3/NOPB, but the netlist and BOM still carry the Microchip part. The new part is listed at DigiKey (product entries 3906441 and 5034443; reel 296-38557-2-ND), but only regional pages were seen and their stock figures conflict: 4,013 (UK), 11,506 (Switzerland), 44,232 (Denmark), 108,067 (Germany); out of stock on the Australia, Canada and Austria pages. The US page, the part status and a price that is not an aggregator's copy were not seen. | When the netlist is updated, read the live DigiKey US page (or Mouser's) before ordering, confirm stock and part status there, and enter the order code of the packaging wanted. No footprint risk is expected from sourcing: it is the 3.3 V member of the family already used for U8. |
| A9 | Main board BOM line 9 (D2 D4 D6 D8 D10 D12 D14 D16, near-infrared LED) | ams OSRAM SFH 4053B was seen in stock in the US at Mouser only (720-SFH4053B; 7,096 in stock; seen on category pages, not on a product page). Its life-cycle evidence conflicts (maker's page: full production; RS: 'being discontinued by the manufacturer'). Its peak wavelength is 850 nm in some extracts and 860 nm in others, and no extract states the 0402 package for the B part. | Keep SFH 4053B as the fitted part and Inolux IN-S42CTQIR as the approved alternative (two parts, two distributors; the Inolux part is dimmer, 5.5 against 9 mW/sr). Read the SFH 4053B data sheet for wavelength, package size, pad layout and polarity mark before the footprint is released. Ask ams OSRAM or Mouser in writing whether the B part is being discontinued. |
| A10 | Main board BOM line 27 (U2 U3, camera cube) | OmniVision OVM7692-RYAA has one maker and one authorised US distributor with stock (DigiKey 884-1027-1-ND: 1,814 and 2,497 in stock on two undated pages; 27.50 at 1; 6.25 at 2,500 on reel; no price in between; lead time 14 weeks on DigiKey's page, 20 weeks on an aggregator). 1000 markers need 2,000 cubes plus losses, more than either stock figure. No end-of-life notice was found, and no maker statement was seen. | Before the layout is frozen, get a written life-cycle statement from OmniVision or DigiKey and a quote at 100 and at 2,000. Buy the EVT and DVT quantity now from DigiKey. For any build above about 800 markers plan on one full reel of 2,500 and a 20-week lead. Treat the part as the first single-source item in the release gates. |
| A11 | Display (off-board, plugs into J1; not a line of the board BOM); design/DESIGN_SPEC.md section 3; design/master_params.yaml lcd.glass | Sharp LS013B7DH03 has one maker and no drop-in alternative; its US shelf stock is not established (undated DigiKey captures today run from 0 to 32,134; Arrow about 1,383; Future 0 with a 2,240 minimum); factory lead time 28 weeks. Its thickness is 0.741 mm in today's extracts against 0.746 mm in the design. | Put the display on the purchasing list that sits above the board BOM. Read the live DigiKey and Arrow pages (or phone) and order the build quantity first, before any other part. Ask Sharp or DigiKey for the life-cycle status in writing. Settle the thickness from the Sharp drawing and correct the design if it is 0.741 mm. |
| A12 | Cell (off-board, soldered to BT1 BT2; not a line of the board BOM) | GM201030-PCB has a single seller (PowerStream, Utah). The listing shows 12.00 each with the protection board, no stock count and no lead time; one extract dates the page 27 September 2024. No second US seller of a protected 2 x 10 x 30 mm cell was found in three searches. The protection board is fitted only on request. | Put the cell on the purchasing list above the board BOM. Ask PowerStream now for a dated quote, stock, lead time, volume prices, the data sheet (length with the protection board, protection thresholds, UN 38.3 and IEC 62133 status) and the name of the cell maker, so that a second route exists. Order in writing as GM201030-PCB. To read the page from a session, www.powerstream.com has to be allowed in the session's network settings. |
| A13 | Main board BOM line 28 (U4, tilt and motion sensor) | The BOM names DigiKey at 4.42 for LSM6DSV16XTR. DigiKey is out of stock (backorder) and today's single-piece price is 5.75. | Change the BOM's Distributor to Newark (62AK1744; 5,212 in stock) or Mouser (5,775 in stock) and the Unit Price to 5.75. |
| A14 | Main board BOM line 29 (U6, flash memory) | The BOM carries the tray code MX25R6435FZNIL0. Today's US stock evidence is mostly for the tape-and-reel code MX25R6435FZNIL0 TR (Arrow US 4,000; Mouser 84 or 10,116 depending on the snapshot); for the tray code only an Arrow France page (3,200) and DigiKey prices without a stock count were seen. | Decide with the assembler whether the BOM carries the tray or the reel code, and name the distributor that stocks that code. |
| A15 | Main board BOM line 10 (J1, display connector) and its Footprint cell | FH12A-10S-0.5SH(55) is the right (top-contact) part and was seen in stock (DigiKey HFK110CT-ND 7,093; Future 24,000; Heilind), but the footprint is the land pattern of the bottom-contact FH12, and no extract confirmed that the FH12A fits it. Two near-identical numbers are wrong: the un-suffixed FH12A-10S-0.5SH is obsolete, and FH12-10S-0.5SH(55) is the bottom-contact part. | Check the land pattern and the 2.0 mm height against the Hirose FH12A drawing before the board is released. Keep the letter A and the (55) suffix in every order document. The fallback connector that amendment E24 names (Hirose FH34SRJ-10S-0.5SH class) has not been searched: source it before the design relies on it. |
| A16 | Main board BOM line 26 (U1, microcontroller); cost roll-up | Only DigiKey shows stock of STM32U585RIT6, and its pages disagree: the US page shows 4,437 in stock at 12.16 for 1 and 7.52 at 500 with a 52-week lead; regional pages show EUR 8.09 at 1 and a 13-week lead. Future shows 4.83 at 160 or more with zero stock. Rev 2 assumed 7.00 at 10. | Read the live DigiKey US page for price and lead time and ask Future for a tray quote. Do not order STM32U585RIT6Q (a different pin-out). |
| A17 | electrical/gl1_main/netlist_out/gl1_main-bom-status.csv and electrical/gl1_cradle/netlist_out/gl1_cradle-bom-status.csv (generated files: correct the source tables) | Several Distributor PN cells still read 'SKU not seen' or 'order by MPN', and several unit prices are below today's listings. The display and the cell are on no parts list. | Enter the order codes seen today: U9 BQ25101YFPR = DigiKey 296-39933-1-ND; U7 MCP1700T-2802E/TT = MCP1700T-2802E/TTCT-ND; RT1 RT2 NCU15XH103F60RC = 490-18149-1-ND; R23 to R27 RC0402FR-0768RL = 311-68.0LRCT-ND; C1 and the other 100 nF = 490-3261-1-ND; cradle R1 R2 RC0402FR-075K1L = 311-5.10KLRCT-ND. Update the unit prices: crystal Y1 from 0.68 to 0.99; IMU U4 from 4.42 to 5.75; Schottky D17 from 0.30 to 0.34. Add the display and the cell to a purchasing list above the board BOM (A11, A12). Three distributor pages carried US tariff notices: refresh every price from a live page before the cost roll-up is reused. |
| A18 | Main board BOM lines 1 to 7 and 13 to 25, cradle BOM lines 1 and 4 (all passives: each names one maker only) | Every passive line is single-sourced in the BOM. | Add an approved-alternates column. Confirmed today: CL05B104KO5NNNC (100 nF), CL05A475MQ5NRNC (4.7 uF), CL05B103KB5NNNC (10 nF), CC0402CRNPO9BN6R8 or C0402C689C5GACTU (6.8 pF), CL05C100JB5NNNC (10 pF), ERJ-2RKF1002X (10 kohm), ERJ-2RKF1003X (100 kohm), YC124-JR-07220RL (resistor array: compare land pattern and height with the Panasonic part first), NTCG103JF103FT1 (thermistor: compare the resistance-temperature table at the charger's and the firmware's thresholds first). Still PROVISIONAL, to be confirmed one by one before they are listed: ERJ-2RKF10R0X, ERJ-2RKF1001X, ERJ-2RKF2201X, ERJ-2RKF33R0X, ERJ-2RKF6811X, ERJ-2RKF1004X, ERJ-2RKF68R0X, ERJ-2RKF4703X, ERJ-2RKF1503X, ERJ-2RKF6041X, and ERJ-2RKF5101X for the cradle. Do not list CL05C6R8CB5NNNC (not found on seven US distributor sites), Bourns CAY10-221J4LF (not confirmed) or 'Bourns CAT16' (a larger array, from memory). |
| A19 | mechanical/README.md part list item 10 (ball feet); amendments E8 and E20; cost roll-up | No current US listing with a grade, a price or stock was found for a 1.0 mm ball in 316 stainless, grade 100, the first material E8 names (the nearest find: Thermo Scientific catalogue number 042018, 1 mm type 316 spheres on a US catalogue page, with no grade or price seen). The rev 2 part, McMaster 1598K16, is 440C, which E8 forbids. The only priced US source found is silicon nitride, grade 5: Boca Bearings '1MM-C SI3N4 BALL GRADE 5 (1 PC)' at 2.37 each, which is 7.11 USD per marker against the 0.30 USD assumed before. | Choose one: make silicon nitride grade 5 the baseline (and check that the potting epoxy bonds to it), or send a request for quote for 1.0 mm 316 grade 100 to Salem Specialty Ball, Hartford Technologies and Thomson Precision Ball (Goodfellow's US site also lists a grade 100 AISI 316 group). In E20 keep +/-0.0127 mm for grade 100 and mark it confirmed (Thomson, Hartford Technologies, US Ball); put the tolerance itself on the purchase order, not only the grade name. Confirm the order code on Boca's page; an aggregator spells it '1MM-C SI3N4 GR.5 BALLS-EA'. |
| A20 | mechanical/README.md part list item 24 (cradle board screws) and post-processing item 7 (pilot holes) | An M2 x 5 screw does not fit the cradle as drawn: 5 mm of screw less the 1.6 mm board leaves 3.4 mm of thread, and the pilot holes are dia 1.6 x 3 deep, so the screw bottoms 0.4 mm before its head seats. The candidate part, McMaster-Carr 96817A207 (5 mm long, head dia 3.35 mm, Torx Plus IP6, pack of 25), has not been confirmed as M2 on McMaster's own page: one extract shows an 'M2.5' heading. | Mechanical owner to choose: drill the pilots 4 mm deep or more if the cradle wall allows it, or specify M2 x 4. Then read the size, length and price on mcmaster.com (96817A209 is the 6 mm length; the length of 96817A204 was not seen). |
| A21 | mechanical/README.md part list item 23 (cradle feet, 'dia 8 x 3') | No self-adhesive bumper of dia 8 x 3 mm was found. The 3M Bumpon SJ5302 is 7.92 mm across and 2.16 mm high: it fits the dia 8.4 x 1.0 pocket but stands 1.16 mm proud where a 3 mm bumper would stand 2.0 mm. | Adopt SJ5302 and correct item 23 and any cradle height that counts a 3 mm foot. Before ordering, find out what the US-page code SJ5302-R25 denotes (5,472 in stock at 0.111 each from 144). If 3 mm is really wanted, read the full catalogue number of the 5/16 in x 7/64 in bumper on McMaster's adhesive-back bumper table. |
| A22 | design/master_params.yaml vent (Gore VE80205); the 50 kPa water-entry requirement in docs/research/enclosure-manufacturing.md | No US listing of VE80205 with a price or stock was found on either search day (2026-11-11 and 2026-11-13), and its water-entry pressure has not been seen anywhere. The alternative looked at, a Porex disc, does not meet 50 kPa in its PMV10 grade (175 mbar minimum, 270 typical), and Porex's stock adhesive discs seen start at 7.0 x 3.0 mm, not 5.0 x 2.0 mm. | Ask Sealing Devices Inc. (Lancaster, New York) and H-O Products for the price, minimum quantity, lead time and water-entry pressure of VE80205. Decide which number governs: 50 kPa, or IP67 (about 10 kPa). If 50 kPa governs, only Porex PMV27 (1,050 mbar typical) clears it with margin, at roughly one thirtieth of the Gore part's air flow (the checker's arithmetic); ask Interstate Specialty Products whether a 5.0 x 2.0 mm disc is a stock item or a custom cut, and in which grade. |
| A23 | Amendments E9 and E19 (quarter-wave film under the cover glass); parts list | The film found, Edmund Optics WP140HE (33.50 USD per 100 x 100 mm sheet), has no adhesive, and its thickness is given two ways: 0.060 +/-0.003 mm on the product page, 0.053 +/-0.003 mm on a data sheet. E19 allows 0.11 mm 'with its adhesive', and no adhesive has been chosen or sourced. | Plan on 0.063 mm worst case for the film, which leaves 0.047 mm: select an optically clear adhesive of the 0.025 mm class (a 0.05 mm one would make 0.113 mm and break E19), add it to the parts list and find a US source. Measure a sheet on receipt. Read the Edmund stock number on the page (44288 may be a page number). Carry the fast-axis mark (a black stripe on the protective film, which is removed before use) to the clocking flat on the die-cut drawing. |
| A24 | Amendment E16; design/master_params.yaml baffle.ring.adhesive; mechanical/README.md part list item 14 (black tape under the baffle ring) | 3M 9495B (0.145 mm) is the only candidate for which US listings were found, and only as full rolls of about 1,700 to 5,100 USD. Only its 0.013 mm carrier is black; the two adhesive layers are clear, so light may travel sideways through the tape under the ring. For tesa 61361 (0.10 mm, black adhesive) no US seller was found. | Buy converter-cut parts of 9495B and measure its light transmission sideways through the bond as well as through the tape, at the red and infrared LED wavelengths, before choosing it. Ask tesa tape, inc. (Charlotte, North Carolina) for a US converter of tesa 61361. Keep the black liquid adhesive as the fallback. |
| A25 | Amendment E22; design/master_params.yaml battery.fixing_adhesive_max (still 0.05); the 'fixing adhesive (0.05 max)' in the height budget of mechanical/README.md; cell fixing tape | Both tapes usually named are 0.058 mm (2.3 mil) without liner: 3M 467MP and, by 3M's own US page, 3M 9460PC, whose '0.05 mm' is a nominal label. Each passes E22's 0.06 mm by 0.002 mm on a typical figure with no tolerance and fails the 0.05 mm still in the YAML. | Change battery.fixing_adhesive_max and the README figure to 0.06 as E22 says, and reword E22 to 'nominal 2 mil class, 0.058 mm typical', or measure a sample. Name 3M 467MP (seen as a narrow 60 yd roll at 70.46 USD); 9460PC has no thickness advantage, is a permanent adhesive and was seen only as wide rolls. If 0.05 mm or less is really needed, the candidates are tesa 4972 (0.048 mm; US seller not confirmed) and 3M 82603 (0.03 mm; no US listing found). |
| A26 | mechanical/README.md part list item 16 (foam pad under the display, 'Poron 4790 class', 0.3 mm) | In what was seen (a converter-hosted data sheet and Rogers' availability booklet) the foam comes at 0.30 mm only as the item PORON 4790-92-30012-04P: the 30 lb/ft3 (480 kg/m3) density, cast on 0.05 mm PET film, with no adhesive. Softer 4790-92 items start at 0.5 mm. No price, stock, minimum order or compression-force figure was seen. | Put the full item code in the design. Check the compression force of the 30 lb grade against the cell-swell allowance, and add the laminated adhesive to the 0.30 mm slot. Ask Stockwell Elastomerics or JBC Technologies for minimum order, lead time, compression force at 25 % deflection, and whether the 0.30 mm includes the PET film. |
| A27 | mechanical/README.md part list item 12 (LCD adhesive frame: '0.15 mm foam-type PSA frame', no product named) | The design names no product for the display frame tape, although the candidate has now been confirmed at 0.15 mm on two search days and can be bought in small rolls. | Record 3M VHB 5906 as the selected tape (DigiKey 6 in x 5 yd roll, seen on regional pages; TapeCase 2 in x 5 yd roll at 53.29 USD). |
| A28 | design/master_params.yaml cover_glass (thickness 1.0, recess_depth 1.25, sub_flush 0.12); production cover glass | 1.0 mm is not a stocked thickness of chemically strengthened glass at either US fabricator seen: Abrisa lists 0.4, 0.55, 0.8, 1.1 and 2.0 mm (Gorilla Glass) and 0.8 and 1.1 mm (Dragontrail); Valley Design lists 0.55, 0.7, 1.1, 1.3 and 2.0 mm. No price or strength figure was seen. | Redesign the stack for 1.1 mm (it would sit 0.02 mm below flush in the present 1.25 mm recess, so deepen the recess by 0.1 mm) or for 0.8 or 0.7 mm. Then request quotes from Abrisa and Valley Design, stating that the 28.0 mm disc must be cut and edged before it is strengthened, and asking for the strength figure. Use the sapphire crystal (Jules Borel, 28.0 x 1 mm, 9.90 USD at 10 or more) only if the E9 sunglasses trial is repeated with sapphire. |
| A29 | design/master_params.yaml visor_window (5.0 x 3.25 x 0.40 mm) | The visor windows are still a quote-only custom part with no price or lead time. | Send the drawing to Valley Design and to Abrisa, asking for the size tolerance (the recess gives 0.25 mm per side), the edge-chipping limit, and whether the coating is applied before dicing. |
| A30 | mechanical/README.md assembly step 12 (cure at 60 C at most) and section 12 (clear potting) | No clear-potting candidate has a maker-recommended full cure at or below 60 C: EPO-TEK 301 is 65 C for 2 h (its 23 C / 24 h cure 'may not achieve' the listed properties), EPO-TEK 301-2 is 80 C for 3 h, and Master Bond EP30-2 gives 24 to 48 h at room temperature as normal but its mixed viscosity is unknown. Fluorescence is documented for none. | Remove EPO-TEK 301-2 from the candidates. Decide whether step 12 may run at 65 C (the cell is not yet fitted at that step), or accept a room-temperature cure and measure hardness, tack and fluorescence on coupons. Ask Epoxy Technology and Master Bond for properties after a room-temperature cure, and Master Bond for the mixed viscosity of EP30-2. |
| A31 | mechanical/README.md section 12 (visor-window adhesive candidates) | No US listing of Dymax 3022-GEL was found on two search days. Dymax 3094-GEL is sold by Ellsworth only in packs of 20 syringes (1,186.75 USD, 21 to 30 business days, no returns); the price rev 2 flagged as a possible error is that pack price. | Drop 3022-GEL, or ask Dymax whether it is a current grade. For the 10-unit build use Dymax Multi-Cure 6-621-GEL (single 30 mL syringes at TestEquity, 112.77 or 121.52 USD, 23-day lead) unless the coupon tests call for 3094-GEL. |
| A32 | mechanical/README.md section 12 (cover-glass rim sealant); assembly step 5 | No single product meets every requirement. MG Chemicals 832FX-450ML is silicone-free and thin enough (700 cP), but is listed at 88 Shore A, which is stiff, and comes only as a 450 mL kit. Dow SE 9187 L Black meets every stated property (1,100 cP, Shore A 17, room-temperature cure) but is a silicone, applied before the later bonds are made. | Designers to decide whether a silicone is allowed on the outside of the tub. Then coupon-test the chosen product on glass and on primed PA12: wicking into a 0.25 x 1.13 mm gap, and contamination of the faces bonded afterwards. Read hardness and cure time in MG's 832FX data sheet first. Do not order MG 832FXT: it is the anti-wicking grade. |
| A33 | Thermal adhesive for RT1 and RT2 (assembly step 13); parts list | Two obvious picks cannot be used: MG Chemicals 8329TCM-6ML is marked no longer manufactured, and Arctic Silver AATA-5G is out of stock at both US sellers seen. | Name MG Chemicals 8329TFF-25ML (silicone-free epoxy, 0.8 W/(m.K), 5-minute working time; Hisco 34.89 USD with 9 in stock). Before release, read its volume resistivity and its room-temperature cure time in MG's data sheet: each dab bridges the two terminals of a temperature sensor. If a longer working time is needed, look at 8329TFS-25ML or 8329TFM-25ML (no US listing seen today). |
| A34 | mechanical/README.md section 12 (primer for the PA12 bonding faces) | 3M Tape Primer 94 and 3M Adhesion Promoter 111 are easy to buy, but both are sold as tape primers, and nothing seen says that 3M recommends either on nylon (PA12) or under an epoxy or a light-cure adhesive. | Read 3M's guidance for its 300LSE tapes (9472LE, 93020LE) on nylon, and ask each liquid-adhesive maker what it wants on PA12, before buying. Until then treat a primer as covering the tape joints only. |
| A35 | mechanical/README.md section 12 (ball-foot potting epoxy, candidate C) | 3M Scotch-Weld DP460 Off-White was seen in stock (Hisco 52.62 USD, 38 pieces), but its viscosity was not seen; stage 1 needs an epoxy that runs round a 1.0 mm ball in a 1.10 mm hole, and from memory DP460 is a thick paste. | Keep DP460 for stage 2 only unless its data sheet shows that it can fill stage 1. Budget the EPX applicator and mixing nozzles that a 50 mL Duo-Pak needs. Do not confuse it with DP460NS (3M ID 7100148751). |

### 12.2 Items carried from rev 2 that are still open

Checked against the design files on 2026-11-13 only where the row says so; otherwise carried as written.

| Rev 2 # | File and place | Finding | State |
|---|---|---|---|
| 3 | `design/DESIGN_SPEC.md` section 4 "PCB" against `electrical/tools/README.md` | The specification says the fine class is 0.10 mm track and gap; the tool's `US_4L_FINE` rule set says 0.09 / 0.09 mm (still so on 2026-11-13). At 0.09 mm every US fabricator checked needs its advanced tier. Amendment E7 now makes the fabricator's written acceptance of 0.100 mm a release gate. | open |
| 4 | `design/DESIGN_SPEC.md` section 7 and the note on status words at its top | The specification says the full list of release gates is kept in `docs/RELEASE_GATES.md`. That file still does not exist (2026-11-13). | closed at revision E (2026-11-18): the specification no longer points to that file; its section 7 is the list |
| 6 | `design/master_params.yaml` `lcd.glass`; `mechanical/README.md` part list item 3 | A Sharp change notice for this display family was reported in rev 2 (not confirmed for this part). With today's 0.741 mm against the design's 0.746 mm, re-confirm the thickness and the bonded surface on current-production panels. | open; see A11 |
| 7, 8, 9, 11 | cover glass, visor windows, vent, foam | Now design actions A28, A29, A22 and A26. | carried into 12.1 |
| 13 | `mechanical/README.md` assembly step 12 | Clear-potting cure temperature: now design action A30. | carried into 12.1 |
| 14 | `mechanical/README.md` section 12 (perimeter seal) | The work-life requirement (an hour or more) excludes most black structural epoxies sold in small cartridges; the US pack of one candidate (400 mL, six per case) is awkward for 10 units. Not re-checked. | open |
| 15 | `design/DESIGN_SPEC.md` section 3 ("DigiKey 884-1027-1-ND, in stock") | Still in the text. DigiKey's own pages showed 1,814 and 2,497 today, undated: say "listed; stock to be confirmed". | closed at revision E (2026-11-18): the specification says so; A10 stays open |
| 16 | `design/master_params.yaml` `battery.body` (34 x 10) | The only near-equivalent cell from the same seller (PGEB021235, 2 x 12 x 35 mm) does not fit this board, and the bay cannot simply grow: a 35 mm cell needs about 39 mm where the board is 35.8 mm wide, and the extra width would use up the gaps to the display connector and the processor. A fallback cell means a new layout or a custom cell of the present size. Not re-checked. | open; see A12 |
| 18, 19 | Mill-Max pin; cell tape | Now design actions A6 and A25. | carried into 12.1 |
| 20 | `mechanical/README.md` section 2 | The printed PA12 base plate (GL1-012) and its die-cut sheet (GL1-031) are needed for 4 of the 10 EVT units; no bureau has been asked whether it can hold thickness and flatness on a 0.87 mm plate. Not re-checked. | open |

### 12.3 Rev 2 items closed by the amendments

- Item 1 (grain LED part numbers missing; infrared LED on last-time buy): closed by E3; follow-up in A9.
- Item 2 (thermistor not recommended for new designs): closed by E2; the new part is VERIFIED.
- Item 5 (parts with no number or rating; no cradle schematic): closed by E6 and by the two netlists; follow-ups in A5, A7,
  A20 and A21.
- Item 10 (ball alloy not stated): closed by E8; follow-up in A19.
- Item 12 (no black tape of exactly 0.13 mm): closed by E16; follow-up in A24.
- Item 17 (no netlist or bill of materials): closed; both boards now have them, and this report follows them.

### 12.4 Suggested buying order

1. Correct the part numbers that cannot or must not be bought as they stand, before anything is ordered: the two capacitor
   numbers (one obsolete, one being discontinued; A1, A2), the cradle fuse (A5) and the spring-pin footprint (A6).
2. Send the requests that cost nothing, all on the same day: OmniVision or DigiKey (camera life-cycle and quote), Sharp or
   DigiKey (display status), PowerStream (cell), Sealing Devices and H-O Products (vent), Salem, Hartford and Thomson
   (stainless balls), Abrisa and Valley Design (cover glass and visor windows), Stockwell or JBC (foam), and Mill-Max (the
   pin drawing).
3. Buy the long-lead, single-source parts for the first two builds together: the display first, then camera cubes, cells,
   the tilt sensor (from Newark or Mouser: DigiKey is out), the flash memory and the microcontroller.
4. Request quotes for the custom work: bare boards, board assembly, base plates, printing, die cutting, prisms in volume.
5. Order the adhesive candidates and run the coupon tests (trial bonds on sample pieces of the real materials) of
   `mechanical/README.md` section 9 before choosing. Allow for lead times: about a month for the window adhesive, two weeks
   for the rim-sealant epoxy.
6. Order the remaining catalogue parts only when the board layout is final, and read a live page for each first: most of
   them showed deep stock, but every figure here is an undated snapshot.

---

## 13. Sources

All were seen as search-result extracts, never as opened pages. Section 13.1 lists the web address attached to each row of
`sourcing.csv` (rows dated 2026-11-13 were seen that day; rows dated 2026-11-11 two days earlier). Section 13.2 lists
further sources of 2026-11-13 used in the text, and 13.3 the further sources of rev 2.

### 13.1 Sources attached to a row

- https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88D/675947
- https://www.digikey.ca/en/products/detail/murata-electronics/GRM155R60J475ME47D/3694656
- https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A105KE15D/965904
- https://www.arrow.com/en/products/grm155r71h103ka88d/murata-manufacturing
- https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H6R8CA01D/3693876
- https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A225KE95D/5027536
- https://www.newark.com/murata/grm1555c1h100ja01d/cap-mlc-10pf-c0g-np0-50v-0402/dp/94AK6915
- https://www.findchips.com/search/VLMS1500-GS08
- https://www.mouser.com/c/optoelectronics/infrared-communications/?mounting+style=SMD%2FSMT&product+type=IR+Emitters+%28IR+LEDs%29
- https://www.digikey.com/en/products/detail/diodes-incorporated/B0530WS-7-F/816523
- https://www.digikey.com/en/products/detail/hirose-electric-co-ltd/FH12A-10S-0-5SH-55/1110331
- https://www.digikey.com/en/products/base-product/vishay-semiconductor-opto-division/751/VEMD8080/264846
- https://www.digikey.com/en/products/detail/onsemi/BSS138LT1G/918376
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-0710RL/726524
- https://www.digikey.com.mx/en/products/detail/yageo/RC0402FR-0710KL/726523
- https://www.mouser.com/en/ProductDetail/YAGEO/RC0402FR-07100KL?qs=mnq%2FyloZIXzTlUn7JAHSWg%3D%3D
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-071KL/726513
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-072K2L/726553
- https://www.digikey.ca/en/products/detail/yageo/RC0402FR-0733RL/729540
- https://www.newark.com/yageo/rc0402fr-076k81l/res-6k81-1-0-063w-thick-film-0402/dp/49AK1568
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-071ML/726515
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-0768RL/726652
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-07470KL/726618
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-07150KL/726542
- https://www.digikey.com.au/en/products/detail/panasonic-electronic-components/EXB-28V221JX/256279
- https://www.digikey.com/en/products/detail/murata-electronics/NCU15XH103F60RC/9686714
- https://www.digikey.com/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579
- https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RYAA/3516559
- https://www.newark.com/stmicroelectronics/lsm6dsv16xtr/inemo-inertial-module-3-6v-smd/dp/62AK1744
- https://www.arrow.com/fr-fr/products/mx25r6435fznil0/macronix-international
- https://www.digikey.com/en/products/detail/microchip-technology/MCP1700T-2802E-TT/MCP1700T-2802E-TTCT-ND/5148837
- https://www.digikey.com/en/products/detail/texas-instruments/LP5907MFX-2-8-NOPB/3906436
- https://www.digikey.ca/en/products/detail/texas-instruments/BQ25101YFPR/5022365
- https://www.digikey.com/en/products/detail/stmicroelectronics/USBLC6-2SC6/1121688
- https://www.digikey.com/en/products/detail/microchip-technology/MCP1700T-3302E-TT/652676
- https://www.digikey.com/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043
- https://www.digikey.com/en/products/detail/yageo/RC0402FR-076K04L/2345144
- https://www.digikey.com/en/products/detail/sharp-microelectronics/LS013B7DH03/425-2903-ND/5300387
- https://www.powerstream.com/li-pol.htm
- https://www.digikey.com/en/products/detail/murata-electronics/GRM155R71C104KA88D/1644733
- https://www.digikey.co.za/en/products/detail/bourns-inc/MF-FSMF020X-2/2039254
- https://www.findchips.com/search/USB4105-GF-A
- https://www.digikey.com.au/en/products/detail/yageo/RC0402FR-075K1L/726624
- https://www.digikey.at/product-detail/en/mill-max-manufacturing-corp/0914-0-15-20-77-14-11-0/ED8185-ND/1147053
- https://www.digikey.co.za/en/products/detail/samsung-electro-mechanics/CL05A105KP5NNNC/3886734
- https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61C105KE01D/5027538
- https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A225KE01D/10695166
- https://www.digikey.com/en/products/detail/murata-electronics/GRT155R61A225KE01D/5416675
- https://www.mouser.com/ProductDetail/Samsung-Electro-Mechanics/CL05A225KP5NSNC?qs=X6jEic/HinAxUPrdb0PbTA%3D%3D
- https://www.mouser.com/en/ProductDetail/Samsung-Electro-Mechanics/CL05B104KO5NNNC/?qs=hqM3L16%2BxlfT2SKOuAUq6Q%3D%3D
- https://www.digikey.com/en/products/detail/samsung-electro-mechanics/CL05A475MQ5NRNC/3889142
- https://www.mouser.com/ProductDetail/Samsung-Electro-Mechanics/CL05B103KB5NNNC?qs=349EhDEZ59pcaIbMQHo3bQ%3D%3D
- https://www.digikey.com/en/products/detail/yageo/CC0402CRNPO9BN6R8/2345080
- https://www.digikey.com/en/products/detail/kemet/C0402C689C5GACTU/2196920
- https://www.digikey.com/en/products/detail/samsung-electro-mechanics/CL05C100JB5NNNC/3886797
- https://www.digikey.com/en/products/detail/panasonic-industry/ERJ-2RKF1002X/192073
- https://www.digikey.com/en/products/detail/panasonic-electronic-components/ERJ-2RKF1003X/192081
- https://www.digikey.com/en/products/detail/yageo/YC124-JR-07220RL/1005537
- https://www.newark.com/tdk/ntcg103jf103ft1/ntc-thermistor-10k-0402/dp/81AH9122
- https://www.digikey.com/en/products/detail/inolux/IN-S42CTQIR/10384804
- https://www.arrow.com/en/products/mx25r6435fznil0tr/macronix-international
- https://www.digikey.com/en/products/detail/texas-instruments/LM66100DCKR/10273183
- https://www.digikey.co.uk/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/5034443
- https://www.digikey.com/en/products/detail/littelfuse-inc/0603L035YR/1920186
- https://www.masterelectronics.com/en/bourns/mffsmf035x2-10751533.html
- https://www.digikey.com/en/product-highlight/b/bourns/multifuse-polymer-ptc-resettable-fuses-mf-nsmf-series
- https://www.digikey.co.uk/en/products/detail/mill-max-manufacturing-corp/0914-1-15-20-77-14-11-0/5361065
- https://www.edmundoptics.com/p/2mm-aluminum-coated-n-bk7-right-angle-prism/2392/
- https://pmoptics.com/Right_Angle_Prisms.html
- https://www.bocabearings.com/products/bearingballtypes/balls/ceramic-silicon-nitride-si3n4-series?ProductType=0
- https://www.esslinger.com/watch-crystal-flat-round-standard-mineral-glass-crystal-1mm-thick/
- https://valleydesign.com/gorilla-glass/
- https://www.photonicsonline.com/doc/precision-xy-saw-cutting-of-glass-wafers-and-filters-0001
- https://h-oproducts.com/product/gore-protective-vents-adhesive-series-ve8-ve7-and-ve9/
- https://www.digikey.com/en/products/detail/3m/SJ5302-R25/7402682
- https://www.mcmaster.com/pt-style-screws
- https://3m.com/3M/en_US/p/d/b40072050
- https://catalog.cshyde.com/printitem/3m-products/3m-adhesive-transfer-tapes/3m9472le
- https://www.digikey.ca/en/products/detail/3m-tc/5906-6-5/5039239
- https://www.testequity.com/product/10029445-7100064639
- https://www.testequity.com/product/445-838-467MP-1
- https://www.jbc-tech.com/media/1334/poron-4790-92-30012-p-extra-softslow-reboundsupported_jbc.pdf
- https://www.edmundoptics.com/p/100-x-100mm-4-retarder-film-wp140he/44288/
- https://www.3m.com/3M/en_US/p/d/v101722005/
- https://www.chemical-concepts.com/product/aralditer-2031-epoxy-adhesive/
- https://eaa.3m.com/3M/en_US/p/d/b40066483/
- https://ellsworth.com/products/adhesives/epoxy/henkel-loctite-hysol-e-30cl-epoxy-adhesive-clear-200-ml-cartridge
- https://media.focenter.com/CMP1007/files/EPOTEK301SpectrallyTransparentEpoxyRoomTemperatureCure8oz_ET301-8OZ_fiberopticcenter_REV2.pdf
- https://www.hisco.com/Product/DP460-50ML-31180
- https://www.testequity.com/product/10000994-6-621-30ML
- https://www.ellsworth.com/products/by-manufacturer/dymax/adhesives/uv-curing/dymax-ultra-light-weld-3094-gel-uv-curing-adhesive-yellow-30-ml-mr-syringe/
- https://products.meridianadhesives.com/storage/downloads/xjagq6xi1luav3sdwj9yuwpee21igy91/301-2-rev-xviii-2.pdf
- https://datasheets.globalspec.com/ds/Master-Bond/ep30-2/bc0f0830-873b-4300-aa6f-c24a19ca3650
- https://dymax.com/products/formulations/light-curable-materials/gasketing
- https://aleo.dymax.com/products/formulations/light-curable-materials/gasketing/ga-112
- https://dymax.com/products/formulations/light-curable-materials/gasketing/ga-142
- https://www.testequity.com/product/10001466-832FX-450ML
- https://ellsworth.com/products/conformal-coatings/silicone/dow-se-9187-l-silicone-conformal-coating-black-330-ml-cartridge
- https://www.edmundoptics.com/p/1-oz-application-bottle-of-noa-61/4209/
- https://www.edmundoptics.com/p/1-oz-application-bottle-of-noa-68/4178/
- https://www.ellsworth.com/products/by-manufacturer/3m/surface-preparation-materials/primer/3m-94-tape-primer-0.66-ml-ampule/
- https://www.ellsworth.com/products/by-manufacturer/3m/surface-preparation-materials/primer/3m-111-adhesion-promoter-250-ml-bottle/
- https://www.hisco.com/Product/8329TFF-25ML-33018
- https://www.digikey.co.uk/en/products/detail/mg-chemicals/8329TCS-6ML/6035512
- https://bayareacircuits.com/pcb-capabilities/
- https://www.macrofab.com/pcba/
- https://www.protolabs.com/services/3d-printing/multi-jet-fusion/
- https://oshpark.com/pricing
- https://3m.com/3M/en_US/converter-solutions-us/applications/prototyping
- https://valleydesign.com/wp-content/uploads/2023/11/schott-d263.pdf
- https://sendcutsend.com/faq/what-is-your-cut-tolerance/
- https://compliancetesting.com/fcc-testing-and-verification/

### 13.2 Further sources seen on 2026-11-13

- Obsolete capacitors and their replacements:
  https://origin-www.findchips.com/detail/grm155r61a105ke15d/Murata-Manufacturing-Co-Ltd ;
  https://www.tti.com/content/dam/ttiinc/products/PCN/Murata/MURATA-OBSL-D10149-A-A3560.pdf (its part list was not in the
  extract) ;
  https://www.futureelectronics.com/p/passives--capacitors--ceramic-capacitors--multilayer-ceramic-capacitors/grt155r61a105ke01d-murata-4201779
  ; https://www.digikey.ca/en/products/detail/samsung-electro-mechanics/CL05A105KP5NNNC/3889162 ;
  https://www.avnet.com/americas/product/samsung/cl05a105kp5nnnc/evolve-5174444/ ;
  https://uk.rs-online.com/p/mlccs-multilayer-ceramic-capacitors/1726818 ;
  https://octopart.com/part/murata/GRM155R61A225KE95D ;
  https://www.digikey.co.uk/en/products/detail/murata-electronics/GRM155R61A225KE01D/13544360
- 100 nF capacitor: https://octopart.com/part/murata/GRM155R71C104KA88D ; https://www.futureelectronics.com/p/4185353 ;
  https://www.ibselectronics.com/part/murata/grm155r71c104ka88d/1768312/ ;
  https://azcus.digikey.com/en/products/detail/samsung-electro-mechanics/CL05B104KO5NNNC/3886659
- 68 ohm resistor: https://www.digikey.hk/en/products/detail/yageo/RC0402FR-0768RL/726652 ;
  https://www.digikey.dk/en/products/detail/yageo/RC0402FR-0768RL/729599 ; https://www.futureelectronics.com/p/8355554 ;
  https://octopart.com/part/yageo-group/RC0402FR-0768RL
- Cradle fuse: https://www.digikey.in/en/products/detail/littelfuse-inc/0603L035YR/1920207 ;
  https://littelfuse.com/%7E/media/electronics/datasheets/resettable_ptcs/littelfuse_ptc_0603l_datasheet.pdf.pdf (its table
  was not in an extract) ; https://www.digikey.co.uk/en/products/detail/bourns-inc/MF-FSMF035X-2/2039255 ;
  https://uk.rs-online.com/web/p/resettable-fuses/6927639 ;
  https://www.digikey.com/en/products/detail/littelfuse-inc/0603L020YR/1920226
- Spring pin: https://www.mouser.jp/mill-max-0914-Series ;
  https://au.element14.com/mill-max/0914-0-15-20-77-14-11-0/connector-type-spring-probe/dp/1654368
- Infrared LED: https://www.mouser.sg/c/optoelectronics/infrared-data-communications/ ;
  https://ams-osram.com/products/leds/ir-leds/osram-chip-led-sfh-4053b ; https://uk.rs-online.com/web/p/ir-leds/0841067
- Camera: https://www.digikey.com/en/products/detail/OVM7692-RYAA/884-1027-1-ND/3190559 ;
  https://www.findchips.com/detail/ovm7692-ryaa/Omnivision-Technologies-Inc ; https://pcxco.com/product/ovm7692-ryaa/ ;
  https://ovt.com/wp-content/uploads/2024/09/OVM7692-PB-v1.8-WEB.pdf
- Display: https://www.digikey.com/en/products/detail/sharp-microelectronics/LS013B7DH03/5300387 ;
  https://octopart.com/part/sharp/LS013B7DH03 ; https://ciiva.com/part/ls013b7dh03-7236082 ;
  https://octopart.com/part/sharp/LS013B7DH06
- Cell: https://www.powerstream.com/thin-lithium-ion.htm ; https://www.ainbattery.com/lipo-customized-battery.html
- Display connector: https://www.digikey.jp/en/products/detail/hirose-electric-co-ltd/FH12A-10S-0-5SH-55/1110331 ;
  https://futureelectronics.com/p/interconnect--ffc-fpc--ffc-fpc-connectors/fh12a-10s-0-5sh-55-hirose-electric-7009729 ;
  https://estore.heilind.com/hirfh12a-10s-05sh55.html
- Charger: https://www.arrow.com/en/products/bq25101yfpr/texas-instruments.html ;
  https://origin-www.findchips.com/search/BQ25101YFPR ;
  https://www.mouser.com/c/semiconductors/power-management-ics/battery-management/?series=BQ25101
- Other electronic parts: https://findchips.com/search/B0530WS ;
  https://www.findchips.com/detail/USBLC6-2SC6/STMicroelectronics ;
  https://origin-www.findchips.com/search/LP5907MFX-3.3%2FNOPB ;
  https://www.digikey.com.mx/en/products/detail/bourns-inc/CAY10-221J4LF/3788494
- Parts named by amendments E25 and E26 (the searches of the review):
  https://www.digikey.com.mx/en/products/detail/texas-instruments/LM66100DCKR/10273183 ;
  https://www.digikey.it/en/products/detail/texas-instruments/LM66100DCKR/10273183 ;
  https://www.digikey.sg/en/products/detail/texas-instruments/LM66100DCKR/10273183 ;
  https://www.digikey.jp/en/products/detail/texas-instruments/LM66100DCKR/10273183 ;
  https://www.digikey.cn/en/products/detail/texas-instruments/LM66100DCKR/10273183 ;
  https://www.digikey.ca/en/products/detail/texas-instruments/LM66100DCKR/10273183 ;
  https://www.snapeda.com/parts/LM66100DCKR/Texas%20Instruments/view-part/ ;
  https://findchips.com/detail/lm66100dckr/Texas-Instruments ; https://www.lcsc.com/product-image/C2869734.html (the only
  find of the first search) ; https://www.digikey.com.au/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/3906441 ;
  https://www.digikey.ch/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/3906441 ;
  https://www.digikey.de/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/3906441 ;
  https://www.digikey.dk/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/5034443 ;
  https://punchouttest.digikey.ca/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/5034443 ;
  https://punchouttest.digikey.at/en/products/detail/texas-instruments/LP5907MFX-3-3-NOPB/5034443 . The pages on which the
  reviewer read 'Active' for LM66100DCKR (TI, Arrow) were reported without their addresses.
- Cradle screws and feet: https://www.mcmaster.com/pt-delta-style-screws ;
  https://www.skdin.com/products/productid-0511FA00021 ;
  https://zoro.com/bsc-preferred-thread-forming-screws-for-thin-plastic-zinc-plated-steel-m2-6-mm-long-ip6-t6-torx-plus-drive-25pk-96817a209/i/G711431312
  ; https://www.skdin.com/products/productid-0505FA00089 ;
  https://www.zoro.com/newport-fasteners-m2-089-x-5-mm-zinc-plated-steel-pan-head-torx-drive-1000-pk-763450-1000/i/G415708246/
  ; https://www.mcmaster.com/bumpon-bumpers
- Ball feet and ball grades: https://www.salemball.com/stainless-steel-316-ball-inventory/ ;
  https://www.thermofisher.com/order/catalog/product/042018.KN ; https://www.chemicalbook.com/Price/CB4660358.htm ;
  https://www.mcmaster.com/product/96415K54/ ;
  https://www.mcmaster.com/products/stainless-steel/performance~bearing-quality/ ;
  https://vxb.com/products/1mm-loose-ceramic-balls-g5-si3n4-bearing-balls ;
  https://www.precisionplasticball.com/1-mm-gr-3-natural-silicon-nitride-si-sub-3-sub-n-sub-4-sub-series-ceramic-precision-balls/
  ; https://thomsonlinear.com/en/product/S60500001C-BOX ;
  https://hartfordtechnologies.com/ball-size-grade-tolerance-definitions/ ; https://acraball.com/grade/ ;
  https://goodfellow.com/usa/grade-100-aisi-316-stainless-steel-balls-group ; https://en.wikipedia.org/wiki/Ball_(bearing)
- Vent: https://uk.rs-online.com/web/p/enclosure-ventilation/2879532 ;
  https://www.gore.com/system/files/2024-07/gore-ptv-adhesive-serie-datasheet-en.pdf (its IP table did not come through) ;
  https://www.interstatesp.com/materials/porex/porex-vents/ ; https://www.porex.com/wp-content/uploads/2023/06/PMV10.pdf ;
  https://www.mouser.com/pdfDocs/AmphenolLTW_PressureReliefVent.pdf ;
  https://www.donaldson.com/en/products/venting/press-fit/
- Glass: https://displaydaily.com/?p=71656 ; https://valleydesign.com/?p=2537 ;
  https://www.julesborel.com/s.nl/it.A/id.12462/.f ; https://www.esslinger.com/round-sapphire-watch-crystal-1-0-mm-thick/
- Tapes, film and foam: https://www.jamindustrialsupply.com/product/adhesive-transfer-tape-9460pc-2/ ;
  https://multimedia.3m.com/mws/media/1851389O (3M F9460PC data sheet) ;
  https://www.ipack.com/tesa-4972-double-sided-transpaent-filmic-tape-p-292018 ;
  https://www.digikey.in/en/products/detail/3m/82600/7673596 ;
  https://multimedia.3m.com/mws/media/871858O/3m-electronic-double-sided-tapes-82600-series.pdf ;
  https://www.tesa.com/en/industry/tesa-61361.html ;
  https://www.gophotonics.com/products/waveplates/american-polarizers-inc/38-416-apqw92-003-pc-140nm ;
  https://www.edmundoptics.com.tw/document/download/510888 ;
  https://marianinc.com/wp-content/uploads/2024/07/PORON-ShockSeal-479079-12-15-20-Density-Data-Sheet-Industrial-Grades.pdf
  ; https://tbpconverting.com/wp-content/uploads/2026/02/Data-Sheet_Rogers-PORON%C2%AE-ShockPad-Foam.pdf
- Adhesives: https://www.testequity.com/product/489-489-7100148768 ; https://www.thorlabs.us/_QLPopup.cfm?PN=NOA61 ;
  https://media.focenter.com/CMP1007/files/1/EPOTEK301SpectrallyTransparentEpoxyRoomTemperatureCure4g_ET301-4G_fiberopticcenter_REV2.pdf
  ; https://at.farnell.com/en-AT/mg-chemicals/8329tcm-6ml/adhesive-2part-epoxy-syringe-6ml/dp/2811936 ;
  https://www.newegg.com/arctic-silver-aata-5g/p/N82E16835100013

### 13.3 Sources carried from rev 2 (seen on 2026-11-11, not re-opened)

These support the rows that still carry the date 2026-11-11 and the carried parts of sections 8, 9 and 12.

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

---

## 14. Appendix: the script behind the counts and the roll-up

`sourcing.csv` holds 132 rows of 17 fields: the 86 lines counted in sections 1.1 and 2.1, 24 alternate, candidate or
superseded electronic parts (group `1-electronics-alternate`; a `bom_ref` that begins "history:" marks a part that is no
longer on a board) and 22 adhesive candidates (group `2-adhesive-candidate`); the last two
groups are not counted as lines. The column `bom_ref` is new in rev 3. The `notes` cell of every row ends with the roll-up
line that the script below reads. Save the script as `rollup.py` and run `python3 rollup.py docs/sourcing.csv` to reproduce
the counts of sections 1.1 and 2.1 and the totals of section 10.1. The script also prints how firm the VERIFIED lines are
(how many were seen on which day, how many showed a stock figure); its header says which words in the csv it counts.

```python
#!/usr/bin/env python3
"""Counts and cost roll-up for docs/sourcing.csv (GreenLine GL-1 sourcing report, rev 3).

Usage:  python3 rollup.py path/to/sourcing.csv

Every costed row ends its 'notes' cell with a tail of this exact form:
    Roll-up: marker x8; q10 $0.620 [seen at 1]; q1000 $0.206 [seen at 3,000].
'marker' or 'cradle' says which product the row belongs to, x8 is the quantity
in one unit, and the words in square brackets say where each price comes from.
A price counts as SEEN only if its bracket starts with the word 'seen'.
Rows that are not costed end with:  Roll-up: not costed (reason).

The script also counts how firm the VERIFIED lines are, from four markers:
  - the date in 'checked_on' (TODAY, or the earlier date of a carried row);
  - a 'stock_or_lead' cell that begins "stock not seen" (listed, no stock figure);
  - the words "Evidence grade:" in 'notes' (the row rests on an aggregator copy or
    a category page, not on a distributor's product page);
  - a 'risk' cell that begins "do not buy" or "superseded".
"""
import csv
import re
import sys
from collections import OrderedDict

TAIL = re.compile(r"Roll-up: (marker|cradle) x(\d+); q10 (none|\$[0-9.,]+) \[([^\]]*)\]; "
                  r"q1000 (none|\$[0-9.,]+) \[([^\]]*)\]\.$")
NOT_COSTED = re.compile(r"Roll-up: not costed \(([^)]*)\)\.$")
LINE_GROUPS = ["1-electronics-marker", "1-electronics-cradle", "2-mechanical", "2-tapes-foam",
               "2-adhesive-class", "3-custom-services"]          # counted as lines
EXTRA_GROUPS = ["1-electronics-alternate", "2-adhesive-candidate"]  # rows, not lines
SERVICES = "3-custom-services"   # outside work: no part number, so no stock figure
TODAY = "2026-11-13"
BLOCKS = OrderedDict([
    ("1-electronics-marker", "Electronic parts, display and cell"),
    ("2-mechanical", "Optics, glass, vent, ball feet"),
    ("2-tapes-foam", "Tapes, film and foam (material)"),
    ("2-adhesive-class", "Adhesives and primer"),
])


def money(text):
    return None if text == "none" else float(text[1:].replace(",", ""))


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        m = TAIL.search(r["notes"])
        r["cost"] = None
        if m:
            r["cost"] = dict(per=m.group(1), qty=int(m.group(2)),
                             q10=money(m.group(3)), b10=m.group(4),
                             q1000=money(m.group(5)), b1000=m.group(6))
        elif not NOT_COSTED.search(r["notes"]):
            raise SystemExit("row without a roll-up tail: " + r["item"])
    return rows


def counts(rows):
    out = OrderedDict()
    for g in LINE_GROUPS + EXTRA_GROUPS:
        sel = [r for r in rows if r["group"] == g]
        out[g] = (len(sel), sum(r["status"] == "VERIFIED" for r in sel),
                  sum(r["status"] == "PROVISIONAL" for r in sel))
    return out


def label(r):
    """Short name of a row: its BOM line if it has one, else the start of its item."""
    ref = r["bom_ref"].split(":")[0]
    return ref if ref.startswith(("main-", "cradle-")) else re.split(r", \d", r["item"].split(" (")[0])[0]


def evidence(rows):
    """How firm the VERIFIED lines are. Returns an ordered dict of lists of rows."""
    lines = [r for r in rows if r["group"] in LINE_GROUPS]
    ver = [r for r in lines if r["status"] == "VERIFIED"]
    parts = [r for r in ver if r["group"] != SERVICES]
    serv = [r for r in ver if r["group"] == SERVICES]
    nostock = [r for r in parts if r["stock_or_lead"].lower().startswith("stock not seen")]
    out = OrderedDict()
    out["verified"] = ver
    out["seen_today"] = [r for r in ver if r["checked_on"] == TODAY]
    out["parts_carried"] = [r for r in parts if r["checked_on"] != TODAY]
    out["services_carried"] = [r for r in serv if r["checked_on"] != TODAY]
    out["parts_with_stock"] = [r for r in parts if r not in nostock]
    out["parts_no_stock"] = nostock
    out["services"] = serv
    out["weak_page"] = [r for r in ver if "Evidence grade:" in r["notes"]]
    out["to_replace"] = [r for r in ver if r["risk"].lower().startswith(("do not buy", "superseded"))]
    out["provisional"] = [r for r in lines if r["status"] == "PROVISIONAL"]
    out["cannot_buy"] = [r for r in out["provisional"] if r["risk"].lower().startswith("do not buy")]
    out["no_product"] = [r for r in out["provisional"] if r["group"] == "2-adhesive-class"]
    return out


def block_of(r):
    c = r["cost"]
    if r["group"] == "3-custom-services":
        name = r["item"].split(" (")[0].split(",")[0]
        return name if c["per"] == "marker" or name.startswith("Cradle") else "Cradle: " + name
    if c["per"] == "cradle":
        return "Cradle: electronic parts" if r["group"] == "1-electronics-cradle" else "Cradle: feet and screws"
    return BLOCKS[r["group"]]


def rollup(rows):
    """Returns (blocks, totals). Each value is [q10, q10 seen, q1000, q1000 seen]."""
    blocks = OrderedDict()
    totals = {"marker": [0.0] * 4, "cradle": [0.0] * 4}
    for r in rows:
        c = r["cost"]
        if not c:
            continue
        b = blocks.setdefault((c["per"], block_of(r)), [0.0] * 4)
        for i, (price, basis) in enumerate(((c["q10"], c["b10"]), (c["q1000"], c["b1000"]))):
            if price is None:
                continue
            amount = price * c["qty"]
            seen = amount if basis.startswith("seen") else 0.0
            for acc in (b, totals[c["per"]]):
                acc[2 * i] += amount
                acc[2 * i + 1] += seen
    return blocks, totals


def main(path):
    rows = load(path)
    widths = {len(r) for r in csv.reader(open(path, newline="", encoding="utf-8"))}
    print("rows %d (plus header); fields per row %s" % (len(rows), sorted(widths)))
    cnt = counts(rows)
    print("\n%-26s %5s %9s %12s" % ("group", "rows", "VERIFIED", "PROVISIONAL"))
    for g, (n, v, p) in cnt.items():
        print("%-26s %5d %9d %12d" % (g, n, v, p))
    lines = [cnt[g] for g in LINE_GROUPS]
    print("%-26s %5d %9d %12d" % ("LINES (first six groups)", sum(x[0] for x in lines),
                                  sum(x[1] for x in lines), sum(x[2] for x in lines)))
    print("%-26s %5d %9d %12d" % ("ALL ROWS", len(rows), sum(x[1] for x in cnt.values()),
                                  sum(x[2] for x in cnt.values())))
    ev = evidence(rows)
    print("\nhow firm the %d VERIFIED lines are" % len(ev["verified"]))
    for key, text, names in (
            ("seen_today", "seen on " + TODAY, False),
            ("parts_carried", "purchased parts carried from an earlier date", True),
            ("services_carried", "outside services carried from an earlier date", False),
            ("parts_with_stock", "purchased parts with a stock figure", False),
            ("parts_no_stock", "purchased parts listed with no stock figure", True),
            ("services", "outside services (stock does not apply)", False),
            ("weak_page", "resting on an aggregator or a category page", True),
            ("to_replace", "can be bought, but the design must or will replace", True)):
        print("  %-52s %3d%s" % (text, len(ev[key]), "  " + "; ".join(label(r) for r in ev[key]) if names else ""))
    print("the %d PROVISIONAL lines" % len(ev["provisional"]))
    print("  %-52s %3d  %s" % ("cannot be bought as named", len(ev["cannot_buy"]), "; ".join(label(r) for r in ev["cannot_buy"])))
    print("  %-52s %3d" % ("adhesive classes with no product chosen", len(ev["no_product"])))
    blocks, totals = rollup(rows)
    print("\n%-58s %9s %9s %9s %9s" % ("cost block (USD per unit)", "q10", "q10 seen", "q1000", "q1k seen"))
    for per in ("marker", "cradle"):
        for (p, name), v in blocks.items():
            if p == per:
                print("%-58s %9.2f %9.2f %9.2f %9.2f" % ((name[:58],) + tuple(v)))
        print("%-58s %9.2f %9.2f %9.2f %9.2f" % (("ONE " + per.upper(),) + tuple(totals[per])))
    both = [totals["marker"][i] + totals["cradle"][i] for i in range(4)]
    print("%-58s %9.2f %9.2f %9.2f %9.2f" % (("MARKER PLUS CRADLE",) + tuple(both)))
    print("\nshare of the total that rests on assumptions (not on a price seen):")
    print("  at 10 units:   %.0f %%" % (100 * (1 - both[1] / both[0])))
    print("  at 1000 units: %.0f %%" % (100 * (1 - both[3] / both[2])))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sourcing.csv")
```


## 15. Appendix: what changed

### 15.1 Since revision 2 (2026-11-11)

- **The electronics rows follow the real bills of materials.** The main board has 37 lines (one of them not fitted) and the
  cradle board 7; rev 2 had 22 and 4 summary lines written before a netlist existed. A new column, `bom_ref`, ties each row
  to its line and to the reference names printed beside the parts (C7, U9 and so on).
- **Rows deleted because the amendments removed the part:** the charger MCP73831T-2ACI/OT (now BQ25101YFPR, amendment E1);
  the thermistor NCP15XH103F03RC (now NCU15XH103F60RC, E2); the infrared LED SFH 4053 (now SFH 4053B, E3); the 440C steel
  balls McMaster 1598K16 (forbidden by E8; now a silicon nitride ball).
- **Rows replaced by exact lines:** 'chip resistors (class)' and 'ceramic capacitors (class)' are now 21 lines with part
  numbers; the cradle's 'fuse, not specified' and '5.1 kohm (class)' are now the parts in the cradle netlist.
- **New rows:** the quarter-wave film of the sunglasses trial and its adhesive (E9, E19); 24 alternate or replacement
  electronic parts (group `1-electronics-alternate`), among them the two parts that E25 and E26 name; eight new adhesive
  candidates.
- **Found wrong, obsolete or mismatched:** two Murata capacitor numbers (one obsolete, one being discontinued); the cradle
  fuse (fails E25); the spring-pin footprint; the M2 x 5 cradle screw (too long for its hole); the cradle feet (no 8 x 3 mm
  bumper was found).
- **Corrected from rev 2:** the price of USD 1,186.75 for Dymax 3094-GEL is a pack of 20 syringes; the PORON foam does exist
  at 0.30 mm, as one specific item; 3M 9460PC is 0.058 mm, not 0.05 mm; the camera prices (27.50 and 6.25) are now seen on
  DigiKey's own page; the display price at 10 is 9.60, not 8.82.
- **Checked twice.** After the five research passes, two independent checkers re-searched 34 of the claims. One alarm was
  refuted (the 68 ohm resistor is not short of stock), one recommendation was refuted (9460PC as the cell tape), and six
  rows were downgraded to PROVISIONAL (two capacitor candidates, the cradle screw, the foam, and two adhesive candidates).
  Section 2 says how to read the result. Section 15.2 lists what a third reading, the review, changed after that.
- **The cost roll-up is now computed by a script from `sourcing.csv`** (section 14): USD 896 for one marker plus one cradle
  at 10 units and USD 144 at 1000 (rev 2: 865 and 134). The rise comes from seen prices replacing lower assumptions
  (microcontroller, tilt sensor, infrared LEDs), from the silicon nitride balls and from the trial film.

### 15.2 In the review of revision 3 (2026-11-13)

An independent reviewer read the finished report against `sourcing.csv` and the design files and reported seven defects. All
seven were accepted, in whole or in part. What changed:

1. **The part that amendment E25 names, LM66100DCKR, is VERIFIED** (it was PROVISIONAL: the first search had found it only
   at a Chinese seller). DigiKey's US page lists it with 53,573 in stock, in the SC-70-6 package, and it is Active. Design
   action A7 now says what remains: working E25 into the netlist.
2. **The part that amendment E26 names, LP5907MFX-3.3/NOPB, is VERIFIED as a listing** on regional DigiKey pages. Its stock
   is marked conflicting (from none to about 108,000); DigiKey's US page was not seen. Design action A8 carries the two
   DigiKey product entries and the reel code.
3. **The count of VERIFIED lines listed with no stock figure was too low.** It was given as 6; it is 13 purchased-part
   lines, and 9 more VERIFIED lines are outside services, where stock does not apply. So a stock figure was seen for 40 of
   the 62 VERIFIED lines. Seven stock cells now begin "stock not seen" like the six that already did, and the script of
   section 14 counts them.
4. **What VERIFIED covers is stated more exactly.** The scoreboard splits the 62 into 49 lines seen on 2026-11-13, 4
   catalogue items and 9 outside services carried from 2026-11-11. VERIFIED is defined for a service. The three lines that
   rest on an aggregator or a category page are named. Five adhesive candidates whose evidence was a data sheet or the
   maker's own page were moved to PROVISIONAL (EPO-TEK 301 and 301-2, Dymax GA-140, GA-112 and GA-142), which leaves 14 of
   the 22 candidates VERIFIED. With the two upgrades above, the csv now holds 96 VERIFIED and 36 PROVISIONAL rows (it was 99
   and 33). The 86 lines are unchanged at 62 and 24.
5. **The design revision is given as amendments E1 to E34**; E29 to E34 name no purchased part. The fallback display
   connector that amendment E24 names (Hirose FH34SRJ-10S-0.5SH class) is now recorded on line main-10, in design action A15
   and in section 11 as not searched.
6. **Sentences that said more than the evidence were reworded.** One capacitor number is obsolete and one is being
   discontinued, not "two no longer made". The 2.2 uF replacement was not seen in stock under its own code, and that it is
   Murata's successor part is an inference, now printed with its basis (A2). "No US listing exists" and "has no US seller"
   became "none was found in the searches made" for the stainless ball, the vent, tesa 61361, the second foam grade and
   Dymax 3022-GEL. The spring pin's stock is said to have been seen on two regional DigiKey pages.
7. **The summary was cut to one page.** The full scoreboard moved to section 2.1, the table of the three risks to section 9,
   the buying order to section 12.4 and the list of changes to section 15.1. The glossary of section 2 grew from 16 entries
   to 43. Not changed: the long rows of the tables in sections 3 to 8 and 12.1, which mirror the cells of `sourcing.csv`.

The cost roll-up did not change: no price or quantity was touched (USD 896 at 10 units and USD 144 at 1000 for one marker
plus one cradle). The corrections used four web searches in two passes (two each), all to confirm the two DigiKey listings
that the reviewer had reported; the second pass saw the same US stock figure for LM66100DCKR and the same Denmark figure for
LP5907MFX-3.3/NOPB again.

### 15.3 Revision 4 (2026-11-18): brought into step with design revision E-EVT1

No search was made and no page was opened. Every listing, stock figure and price is the one of revision 3. What changed:

1. **The board lines are the revision E parts lists.** Line 3 is Samsung CL05A105KP5NNNC and line 6 Murata
   GRM155R61A225KE01D (they were "replaces" rows); U11 is TI LP5907MFX-3.3/NOPB (line 34); the ideal-diode switch U12, TI
   LM66100DCKR, is line 35; the cradle fuse F1 is Littelfuse 0603L035YR. The five parts that left (GRM155R61A105KE15D,
   GRM155R61A225KE95D, B0530WS-7-F at D17, MCP1700T-3302E/TT, MF-FSMF020X-2) are history rows in sections 3.1 and 4.1.
2. **The labels `main-NN` are the revision E BOM item numbers.** D17's line 10 is gone, so the labels main-11 to main-35 of
   revision 3 are one lower throughout this report, section 15.1 and 15.2 included, and U12 is main-35. The status BOMs now
   find a line's row by its references, and report a row whose part number or number is out of step.
3. **Counts.** 64 of the 86 lines are VERIFIED (62 before) and 22 PROVISIONAL (24): the two capacitor lines now name parts
   whose listings were seen. No row changed its status word; the csv still holds 96 VERIFIED and 36 PROVISIONAL rows.
   VERIFIED still means only that a listing was seen.
4. **Cost.** USD 896.12 at 10 units and USD 144.52 at 1000 for one marker plus one cradle (896.11 and 144.47): the diode
   and the MCP1700 are no longer priced, U12 and the LP5907 are. The LP5907's prices are aggregator figures and are not
   counted as seen, so the share resting on assumptions at 1000 units rose from 69 % to 70 %.
5. **Cradle (amendment E36).** The board is 1.0 mm thick, its spring-pin holes are 0.80 mm finished, and the model calls
   for M2 x 4 screws. The 5 mm McMaster part of revision 3 is no longer a candidate, and no 4 mm part number has been seen:
   the screw line stays PROVISIONAL.
6. **Section 12.0 is new:** the state of each design action at revision E. Items 4 and 15 of section 12.2 are closed.
7. Not re-read for revision 4: sections 5 to 9 (except the two cradle rows), 10.5, 12.2 to 12.4 and 13.
