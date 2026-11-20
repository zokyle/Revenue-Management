# GreenLine GL-1: compliance checklist (US market first)

Checklist revision 3, 2026-11-20. Written against `design/DESIGN_SPEC.md` rev E (EVT1,
amendments E1 to E36) and `design/master_params.yaml` rev E-EVT1.

Revision 3 is revision 2 of 2026-11-11 brought into step with the revision E design. **It made
no web search and opened no page.** Every legal point, date and source below is still the
reading of 2026-11-11 and keeps the label it had then. What changed is the description of the
design (section 1), the rows whose gap an amendment has closed (rows 5, 11, 12, 14, 15, 16, 18,
21, 27, 28, 29, 32), and section 4. Section 10 lists the changes.

**Read this first.**

- Nothing in this project has been built or tested. No compliance test has been run, no
  document has been collected from any vendor, and nothing has been filed anywhere. The
  status of every line below is **Not started**.
- "In the design at revision E" means that the specification, the drawings, the board files or
  the firmware source now carry a thing. It does not mean that the thing exists as hardware or
  that it works. Firmware results quoted here come from a simulator on a PC, and currents come
  from a model built on data-sheet figures, many of them from memory.
- This is an engineering checklist. It is not legal advice (section 9). Every test question in
  it is to be confirmed by an accredited test lab, and every reading of a law by an attorney,
  before anything is printed, ordered, shipped or filed.
- An earlier research note, `docs/research/rules-compliance.md`, could not reach the web and
  marked everything unverified. It was also written for a version with a Bluetooth radio. The
  GL-1 has **no radio**. This checklist re-checks the points that still apply and drops the
  ones that do not.

## How to read the labels

| Label | Meaning |
|---|---|
| **VERIFIED** | Seen on 2026-11-11 in the text a web search returned from the named source. Regulator and vendor pages could not be opened directly, so "seen" means the search extract, not the whole page. Read the full page before acting. |
| **PROVISIONAL** | From memory, from the earlier unverified research, or from an extract that did not show the exact point. Must be confirmed before anything is printed, ordered or filed. |
| **Not found** | Looked for on 2026-11-11 and not found. No value was invented. |
| **REPO** | A fact about the design, taken from the design package. The file is named. |
| **PROPOSED** | Suggested by this checklist, or stated in the specification as a requirement that no measurement supports yet. |
| **In the design (rev E)** | The design files now carry it, and the amendment is named (E1 to E36). Not built and not tested. |
| **NOT MET (model)** | The firmware's own test log records that a requirement is missed in its model. A model result, not a measurement. |
| **Reported in review** | A second review ran its own web searches on 2026-11-11. Revision 2 could not repeat them (its search allowance was used up and regulator pages could not be opened), and revision 3 made no search. A point marked this way is **PROVISIONAL** until someone reads the source (listed as [C29]). |

"By whom" uses five words: **Design** (the design team: electronics, firmware, mechanics),
**Test lab** (an outside laboratory), **Vendor document** (a paper the part maker or seller
must supply), **Owner** (a business decision or filing only the owner can make), **Attorney**
(needs a qualified lawyer).

## Words used

| Word | Plain meaning |
|---|---|
| FCC | Federal Communications Commission. Sets the US rules for radio interference. |
| Unintentional radiator | A device that is not meant to send radio waves but leaks some anyway, because fast electronic clocks act like tiny transmitters. |
| SDoC | Supplier's Declaration of Conformity. The maker has the product tested, keeps the report, and declares that it complies. Nothing is filed with the FCC. |
| CFR | Code of Federal Regulations: the numbered US rule books. "47 CFR 15.101" means title 47, part 15, section 101. |
| UN 38.3 | A set of eight abuse tests (altitude, heat, shock, short circuit and others) that every lithium cell type must pass before it may be shipped. |
| Test summary | A one- or two-page paper from the cell maker stating that the cell type passed UN 38.3. |
| CPSC | Consumer Product Safety Commission. The US agency for the safety of consumer goods. |
| Prop 65 | A California law that requires a warning when a product can expose people to chemicals on a state list. |
| RoHS, REACH | European rules that limit certain hazardous substances in electronics (RoHS) and require disclosure of others (REACH). |
| FTC | Federal Trade Commission. Polices advertising claims, including "Made in USA". |
| USGA, The R&A | The two bodies that write the Rules of Golf. |
| FTO | Freedom to operate: a lawyer's search for other people's patents that the product might infringe. |

---

## 1. The facts about the product that decide which rules apply

| Fact (REPO) | Where | Why it matters |
|---|---|---|
| No radio of any kind. No Bluetooth, no Wi-Fi, no wireless charging | `DESIGN_SPEC.md` section 3 | No FCC transmitter certification, no FCC ID, no Bluetooth listing. Only the rules for unintentional radiators remain |
| A processor that runs at up to 160 MHz during a read, a 48 MHz USB clock, a 12 MHz camera clock, two cameras, fast data lines | `DESIGN_SPEC.md` section 4 | These are the "tiny transmitters". 160 MHz is the highest frequency and sets how far up the lab must measure |
| USB (full speed) to a PC, through a charging cradle with spring pins. The cradle board has a USB-C socket, a 5.1 kilohm resistor from each of its two CC pins to ground, a resettable fuse and a static-discharge clamp (E6) | `DESIGN_SPEC.md` sections 3, 4 (E6) and 5; `electrical/gl1_cradle/out/spec_rules.md` | In the cradle the marker is a computer accessory, tested together with cradle and cable |
| One lithium-polymer pouch cell, 2 x 10 x 30 mm, about 43 mAh at 3.7 V: about 0.16 Wh (our arithmetic). Soldered to the board. The housing is glued shut | `DESIGN_SPEC.md` sections 3 and 5 | Transport rules, safety papers, battery laws. A pouch, not a coin cell. Not removable by the user |
| Charged at about 20 mA (19.8 mA by the setting resistor) from 5 V. The charger chip (TI BQ25101, E1) has its own temperature sensor on the cell and is meant to stop a charge outside its temperature window with no firmware running. The firmware adds a narrower window of 0 to 45 C through a second sensor (E2), and stops any charge after 6 hours (E32). The chip's thresholds and ball map are PROVISIONAL: its data sheet has not been read | `DESIGN_SPEC.md` section 4 ("Charger (E1)", "Cell temperature (E2)"); `firmware/README.md` "Charger and cell temperature (rev E)" | Charger safety and energy rules |
| Eight red and eight infrared LEDs under the base, facing the turf, behind clear resin | `DESIGN_SPEC.md` sections 3 and 4 | Eye-safety file. No laser |
| It measures slope and draws an aim line | `DESIGN_SPEC.md` sections 1 and 2 | Not allowed during a round under the Rules of Golf |
| It has no switch and wakes when moved. A ship mode exists since E13: after a command sent through the cradle the marker stays in its lowest state, with the motion wake-up off, until it is next given power in a cradle. No camera read is started when the cell reads above 60 C (E13) | `DESIGN_SPEC.md` section 6 (E13); `firmware/README.md` "Cradle, ship mode and the hot cell" | Transport (switching on in the box), shelf life, heat |
| Two places for printed or displayed statements exist since E10: a legend printed on the underside of the base plate (maker, model, "Practice device", two statement blocks (capacity CONTRADICTED in the package: 88 characters for the two blocks together, 44 each, by `mechanical/README.md` section 4 item 9 and section 12; 88 each by the wording of `DESIGN_SPEC.md` E18 and of the YAML comment; `docs/RELEASE_GATES.md` G-045), a box for the serial number), and an INFO screen in the firmware (4 text pages, 684 character cells in all). **Both hold placeholder text** | `DESIGN_SPEC.md` section 5 (E10, E18); `mechanical/README.md` section 4, item 9; `firmware/README.md` "The regulatory and information screen" | Labels and required statements |
| Printed nylon (PA12) shell, FR-4 base plate, a fluoropolymer (ePTFE) vent, tapes, and adhesives in nine classes of which none has a product chosen yet. Boards assembled lead-free with RoHS-compliant parts (E5). The country of manufacture is recorded for 3 of the 86 lines of the sourcing list, and none of the three is the US | `DESIGN_SPEC.md` sections 4 (E5) and 5; `docs/SOURCING.md` sections 1.4 and 7 | Materials questions and origin claims |
| A product for adult golfers. Not a toy, not aimed at children | `DESIGN_SPEC.md` section 1 | Keeps it out of the children's product rules. The marketing must not change that |

---

## 2. The US checklist

Status of every row: **Not started.**

### 2.1 Radio interference (FCC)

An unintentional radiator is like a car engine. Its job is to turn the wheels, yet the
neighbours still hear it. The FCC rule sets how "loud" the electronics may be in the radio
bands, and asks the maker to prove it by measurement.

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 1 | FCC 47 CFR Part 15, Subpart B: which procedure | The GL-1 is a digital device for home users (Class B). It needs an equipment authorization before it is marketed. The rule's table lists "Other Class B digital devices & peripherals: SDoC or Certification"; a compilation of the same table shows the same two choices for Class B personal-computer peripherals. So **SDoC is allowed**. It is the simpler path: test, keep the report, declare. No FCC ID | Choose SDoC. Name the US "responsible party" (row 3) | Owner | Written decision in the compliance file | Not started | VERIFIED [C1] (table rows as extracted from eCFR and a 2026 compilation; read the full table) |
| 2 | The emissions test | Radiated emissions must be under the Class B limits (47 CFR 15.109). Because the highest clock is 160 MHz, the scan runs from 30 MHz to 2 GHz (47 CFR 15.33). Conducted emissions on the mains side are measured when the product is run from a mains-powered USB supply (47 CFR 15.107) | Test two set-ups: (a) the marker alone, doing reads in a loop; (b) the marker in the consumer cradle, charging, with USB data running to a PC through a typical cable. Do a cheap pre-scan on an EVT unit first (`VALIDATION_PLAN.md` test R1); the formal test is on a production-intent unit | Test lab; Design supplies a test firmware that reads in a loop | Test report naming the unit, firmware version, cradle and cable | Not started | PROVISIONAL (frequency range and section numbers from memory; the search confirmed only that 15.33 holds the table). Limits: PROVISIONAL |
| 3 | Responsible party | For SDoC the responsible party must be located in the United States, and is named in the paperwork with a name, address, and telephone number or internet contact | Decide which US person or company this is. They keep the records and answer the FCC | Owner | Name and address on file | Not started | VERIFIED [C2] |
| 4 | Which lab | SDoC has not needed a specially recognised lab in the past. That is changing. Since 8 September 2025, labs owned or controlled by certain foreign entities are barred, SDoC included. On 29 or 30 October 2026 the FCC was reported to have adopted further limits on foreign test labs; whether SDoC tests must now come from an accredited lab was reported differently by different law firms | Use an accredited lab in the US. Ask the lab, in writing, whether its report is acceptable for SDoC under the rules in force on the test date | Owner; Test lab | Lab's accreditation certificate and its written answer | Not started | VERIFIED for the 2025 rule and for the report of an October 2026 order [C5]; the SDoC detail and any dates: **PROVISIONAL** |
| 5 | Label on the product | The device (or, in some cases, its manual and packaging) must carry the statement that begins "This device complies with part 15 of the FCC Rules." A small-device exception exists: when the statement cannot be printed in a font of four points or larger **and the device has no display that could show it**, the text goes in the manual and also on the packaging or on a removable label. **In the design (rev E):** the gap "no place for the statement" is closed by E10. The base plate carries a legend with two statement blocks at a text height of 1.0 mm (capacity CONTRADICTED in the package: 88 characters for the two blocks together, 44 each, by `mechanical/README.md` section 4 item 9 and section 12; 88 each by the wording of `DESIGN_SPEC.md` E18 and of the YAML comment; `docs/RELEASE_GATES.md` G-045), and the firmware has an INFO screen of 4 text pages (684 character cells; capitals, digits and punctuation only). The mechanical notes record that the short first sentence fits a block and the full statement with its two conditions does not. Both places hold placeholder text, and the firmware's release check refuses a release build while they do | The GL-1 is small **and has a display**, so read the full paragraph before relying on the exception. Three routes remain: (a) print the statement in the legend blocks, if the required words fit: one block holds 44 characters by the mechanical notes and 88 by the specification's wording, so count the character cells on drawing GL1-011 first; (b) show it on the INFO screen (an "e-label") and print it on the packaging; (c) confirm that manual plus packaging is enough. Decide, then freeze the words from the regulation text and enter them in the legend artwork and in `firmware/app/gl_regulatory.h`. Confirm the fabricator's legend print rules with the quote (E18) | Design; Owner | Artwork or screen capture; the paragraph it relies on | Not started | VERIFIED [C3] for the statement's first sentence and the small-device paragraph. Whether the two-condition sentence is still part of the required text: **PROVISIONAL** (the extract did not show it). E-label rules (47 CFR 2.935): PROVISIONAL. REPO: `DESIGN_SPEC.md` section 5 (E10, E18); `mechanical/README.md` section 4, item 9; `firmware/README.md` "The regulatory and information screen" |
| 6 | Text in the user manual | Three pieces. (i) The SDoC "compliance information": product name and model, the part 15 statement, and the responsible party's contact details; in the manual or on a separate sheet. (ii) The Class B notice to the user, which says the limits protect against interference in a home and lists what the user can try if interference occurs (in older editions of the rule it begins "This equipment has been tested and found to comply with the limits for a Class B digital device"). (iii) A caution that changes not approved by the responsible party could void the user's authority to operate the equipment | Copy all three **word for word from the current regulation text** on the day the manual is frozen. Do not copy them from this file or from another product's manual | Owner (text); Design (manual layout) | Manual proof with the three texts marked | Not started | VERIFIED that all three are required: [C2] (2.1077), [C4] (15.105 and 15.21, which covers unintentional radiators). Exact current wording: **PROVISIONAL** |
| 7 | Exemptions | Part 15 exempts a few kinds of digital device (47 CFR 15.103), for example ones whose highest frequency is under 1.705 MHz and that never connect to the mains. None fits a 160 MHz, USB-connected consumer product | Record in the file that no exemption is claimed | Owner | One line in the file | Not started | PROVISIONAL (list from memory; the section was not seen on 2026-11-11) |
| 8 | No radio, and keeping it that way | No transmitter rules apply as designed. A later Bluetooth version would bring back transmitter certification and the Bluetooth listing fee | Any change that adds a radio, a wireless charger or an NFC tag reopens this section | Design | Change control note | Not started | REPO: `DESIGN_SPEC.md` section 3 |

### 2.2 Battery: transport and safety papers

UN 38.3 is like a crash-test certificate for a type of cell. The carrier does not test your
parcel; it relies on the paper that says this cell type passed.

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 9 | UN 38.3 test summary | Every maker, and every later distributor, of lithium cells made since 2008 must make a test summary available. The rule took effect on 1 January 2022 (49 CFR 173.185(a)(3)). The summary has no expiry; a new one is needed only if the cell design changes. The seller's listing prints "UN38.3" against the bare cell; no document has been seen | Get the test summary for the exact cell **with** its protection board, before any cell is ordered in quantity. Check that the part number, the watt-hour rating and the maker's name on it match what is delivered | Vendor document | The test summary (PDF), filed with the lot records | Not started | VERIFIED [C6]. Listing note: REPO, `docs/SOURCING.md` 9.3 |
| 10 | How the finished product ships | A marker with its cell inside ships as "lithium ion batteries contained in equipment" (UN3481). The cell is about 0.16 Wh, far under the 20 Wh limit for the small-cell exceptions of 49 CFR 173.185(c). The regulator has treated a package with only a few cells installed in equipment as needing no lithium battery mark. The first extract read "fewer than four cells, or two batteries". Reported in review, as the rule's own words quoted in the regulator's letters: the mark is not required for **no more than four lithium cells or two lithium batteries contained in equipment, where there are no more than two packages in the consignment**. A GL-1 package holds one cell, so one or two boxes need no mark on either wording. Three or more boxes in one shipment need it, if the two-package condition reads as quoted | Write a one-page shipping instruction: classification, packing, when the mark is needed. Ask each carrier (ground and air) for its own rules. Put the mark on any shipment of more than two packages | Owner | Shipping instruction; carrier acceptance in writing | Not started | VERIFIED [C7] for the 20 Wh limit and the regulator's letter on the mark. The exact words of the exception, with its two-package condition: reported in review [C29], not re-opened by this revision, so **PROVISIONAL** until read on the official page. UN number and packing details: **PROVISIONAL** |
| 11 | Air transport | The airline rule book (IATA) covers this case in packing instruction 967. For cells contained in equipment a charge of no more than 30 % is **recommended** in 2026, not required. The requirement that began on 1 January 2026 is for cells packed beside equipment and above 2.7 Wh | Ship at about 30 % charge anyway, in ship mode (row 12). Two things are missing. (1) **A way to set the charge at the factory:** the firmware has no command for it; the PC watches the cell voltage and stops the charge, and the voltage that stands for 30 % is not defined (`MANUFACTURING_PLAN.md` section 7.4). (2) **Shelf life.** The specification asks for no more than 5 microamps in ship mode and at least 3 months from a 30 % charge (E23, PROPOSED until measured). The firmware's supply model gives 12.9 microamps plus the display panel, for which no figure is known, and 42 days from 30 %: **NOT MET (model)**. Asleep without ship mode the model gives 23.7 microamps and 23 days from 30 %. All of these are model figures; none is measured (`VALIDATION_PLAN.md` test Q1). The choices are a hardware change to the always-on parts, a shorter shelf limit with recharging of stock, a higher shipping charge (30 % is a recommendation, on this row's reading), or a "charge before first use" card | Owner; Design | Packing record showing the charge level; the measured shelf life | Not started | VERIFIED as a training provider's summary [C8]; the rule book itself was not seen. Shelf-life figures: REPO, `firmware/README.md` "Cradle, ship mode and the hot cell" and "Sleep and the supply model (rev E)"; requirement: `DESIGN_SPEC.md` section 6 (E23) |
| 12 | Switching itself on in the box | Equipment shipped with a cell inside must be protected against switching on by accident (recalled from the air rules). The GL-1 has no switch: it wakes when moved and runs a read with its cameras on. **In the design (rev E):** ship mode (E13). A command through the cradle arms it; one second after the marker is lifted out, the processor enters its lowest state with the motion wake-up off, and only power from a cradle wakes it. On the simulator a minute of handling does not wake it. It has never run on hardware | Three things remain. (1) Measure the ship-mode current on EVT units: the model misses the requirement (row 11). (2) Write the packing step that arms ship mode and proves it: a reset disarms it, so the check comes last (`MANUFACTURING_PLAN.md` section 7.4). (3) Tell the buyer, on the quick-start card, that the marker must be put in its powered cradle once before it works. Confirm the transport rule itself (PROVISIONAL) | Design; Owner | Firmware release note; test record; packing instruction | Not started | Rule: **PROVISIONAL**. Behaviour: REPO, `DESIGN_SPEC.md` section 6 (E13); `firmware/README.md` "Cradle, ship mode and the hot cell" |
| 13 | Cell safety certificate to ask the vendor for | US federal law sets no general safety standard for a lithium cell inside a product of this kind (as far as was found). Retailers and marketplaces ask for one anyway. The papers in use: **IEC 62133-2** or its US twin **UL 62133-2** (cell and pack tested together), **UL 1642** (the cell alone), **UL 2054** (battery packs). One lab states that a single-cell pack cannot be tested to UL 2054 and goes to UL 62133-2 instead. For this cell only the "UN38.3" note has been seen; no UL 1642 or IEC 62133 statement | Ask the seller for an IEC 62133-2 (or UL 62133-2) report or certificate covering the cell with its protection board, or failing that a UL 1642 certificate for the bare cell. If none exists, budget a test at a lab or choose another cell. Also ask for the protection limits, the highest charge current and the temperature limits | Vendor document; Test lab if the vendor has none | Certificate or full test report, matching the part number | Not started | VERIFIED as lab and trade-press summaries [C9]. "No federal standard": **PROVISIONAL**. Vendor status: REPO, `docs/research/bom-verification-opto.md` 3.4 |
| 14 | Charging: 5 V only, and only when the cell is not too hot or too cold | The cradle has a USB-C socket and no power-negotiation chip, so a proper USB-C source stays at 5 V. The charger chip sets about 20 mA and stops at 4.2 V. **In the design (rev E):** the two gaps of revision D (nothing watched the cell while the processor's built-in USB loader ran, or for up to 33 s after a firmware hang) are closed by E1: the charger chip has its own temperature sensor and applies its own window whatever the processor does. What stands: (a) in those two states the limit is the chip's window, which the firmware's model takes as 0 to 60 C with a lower end voltage of 4.06 V above 45 C, not the firmware's 0 to 45 C: **NOT MET (model)** for the 45 C limit. (b) Those thresholds, and the chip's ball map, are PROVISIONAL: the data sheet has not been read. (c) If the chip's own sensor breaks off, the model charges with no temperature window, no timer and no end of charge while no firmware runs. (d) The cell maker's charging temperature limits have not been seen (row 13) | Read the BQ25101 data sheet against the sensor chosen. Get the cell data sheet and decide whether charging between 45 and 60 C at the reduced voltage is acceptable for this cell. Show at EVT that the cell never charges outside the limits decided (`VALIDATION_PLAN.md` tests J1 to J6 and J10) | Design; Owner for the decision in (a) | Test records; the decision; the two data sheets | Not started | REPO: `DESIGN_SPEC.md` section 4 (E1, E2, E32); `firmware/README.md` "Status - read this first" and "Host simulator (`hal/host`)", which describes the charger model |
| 15 | USB-C socket details | A USB-C socket on a device that takes power needs a 5.1 kilohm pull-down resistor on each of its two "CC" pins. Without them a USB-C charger with a C-to-C cable may give no power at all. A plain USB 2.0 port offers up to 500 mA at 5 V. **In the design (rev E):** the gap is closed by E6. The cradle board carries the two resistors (R1, R2), a resettable fuse (F1) and a static-discharge clamp, and the board's rule check passes on all three. The fuse on the board holds 0.35 A and trips at 0.75 A, with 1.0 ohm at most after a trip and a 6 V rating (listing data, PROVISIONAL) | Decide two points the sourcing report leaves with the designers (its action A5): the fuse trips at 0.75 A where the first proposal said about 0.5 A, so on a source limited to 0.5 A a hard short is ended by the source and not by the fuse; and a 6 V rating has no margin over a 5.5 V bus. The fuse covers a hard short across the pins only; it does not react to the 0.1 to 0.6 mA that a film of water in the pad slot is estimated to pass. Confirm the socket's land pattern against its maker's drawing. Test on three kinds of USB source and with a short across the pins (`VALIDATION_PLAN.md` test J9) | Design | Cradle schematic; test record | Not started | VERIFIED as chip makers' application notes [C10]. REPO: `DESIGN_SPEC.md` section 4 (E6, E25); `electrical/gl1_cradle/out/spec_rules.md` (rows CC, fuse, ESD); `docs/SOURCING.md` section 12, A5 |
| 16 | USB identity | A commercial USB device needs its own vendor and product numbers. None is assigned. The firmware carries named placeholders, and since E34 its release check refuses a release build while they are in place | Obtain a vendor ID or a sub-licensed product ID. The USB logo may only be used after the USB organisation's own testing | Owner | Assignment letter | Not started | PROVISIONAL (from memory). REPO: `DESIGN_SPEC.md` E34 and section 7; `firmware/README.md` "Boot stub (E34)", item "USB ids" |
| 17 | Charger energy rules | A federal energy standard for battery chargers exists (10 CFR 430.32(z), in force for products made since 13 June 2018) and the rule-making covered USB-charged devices. In May 2025 the Department of Energy proposed to cancel it. Whether that became final was **not found**. California has its own battery-charger rules | Treat the federal standard as applicable until shown otherwise. Ask a lab whether this product is in scope, what the test is, and what must be filed federally and in California | Owner; Test lab | Lab's written scope opinion; test report and filings if in scope | Not started | VERIFIED [C18] for the standard and the proposal to cancel it. Final status: **not found**. Scope for this product and the California rules: **PROVISIONAL** |

### 2.3 Consumer product safety (CPSC)

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 18 | Duty to report a hazard | Makers, importers, distributors and retailers must tell the CPSC within 24 hours of obtaining reportable information: that a product fails a CPSC rule, or has a defect that could create a substantial hazard or an unreasonable risk of serious injury or death. No injury needs to have happened. The agency's advice is "when in doubt, report". An overheating or swelling cell is the obvious case here | Before the first sale: a written procedure. Who receives complaints, who decides, who reports, how units are traced (serial number, lot records). Keep every safety complaint. **In the design (rev E):** each unit has a 7-character serial number, shown on the INFO screen and marked by hand in a box of the base-plate legend. It is derived from the processor's built-in number, not assigned, so two units can share one (the firmware notes give about 1.2 % that any two of 10,000 do); the processor's own number is the identity of record. Decide whether that is enough for a recall, or whether an assigned number is needed | Owner | The procedure; a complaint log | Not started | VERIFIED [C11]. REPO: `firmware/README.md` "Calibration records", item "Serial number"; `mechanical/README.md` section 4, item 9; `MANUFACTURING_PLAN.md` section 7.3 |
| 19 | Certificates | A General Certificate of Conformity is required only for a general-use product that falls under one of the CPSC's listed rules. No listed rule was identified for an adult golf training device with a sealed pouch cell. If none applies, no certificate is needed, and the electronic filing duty for imports that began on 8 July 2026 does not arise | Have the conclusion "no listed rule applies" checked once by someone qualified, and file the answer. Keep the product clearly an adult product: no marketing to children of 12 or under, which would bring in the children's product rules | Owner; Attorney | Written conclusion in the file | Not started | VERIFIED [C12] for the principle and the filing date. That no rule applies to this product: **PROVISIONAL** (our reading) |
| 20 | Reese's Law, 16 CFR Part 1263, UL 4200A (button and coin cells) | **What was found:** the law covers "a single cell battery with a diameter greater than the height of the battery", and any other battery that the Commission determines to be an ingestion hazard. The one carve-out seen concerns zinc-air cells. **Nothing was found** in which the CPSC says whether a rectangular lithium-polymer pouch cell is in or out. **Our reading:** a 2 x 10 x 30 mm rectangular pouch has no diameter, is soldered in, and sits inside a glued housing that cannot be opened without destroying it, so it is not a button or coin cell and the rule does not apply. That is a reading, not a ruling | Ask the CPSC's small business office the question in writing and keep the answer. Do not add a coin cell in any later revision without re-opening this row (the specification already says "No coin cell") | Owner | The CPSC's written reply | Not started | VERIFIED [C13] for the definition. Applicability to a pouch cell: **not found**; our reading is PROVISIONAL |
| 21 | Instructions and warnings | No single federal rule sets the text. Common sense and the cell data ask for: do not open, crush or heat; do not leave in a hot car or on a dashboard; charge only between 0 and 45 C and only in the supplied cradle; dry the marker before docking; stop using it if it swells or gets hot; how to dispose of it. EVT units also need "not step-proof". Since E13 two more lines belong in the guide: the marker shows "TOO HOT" and takes no read when its cell is above 60 C, and a new marker must be put in its powered cradle once before it works (it leaves the factory in ship mode) | Write the warnings from the cell maker's data sheet once it is in hand. Put the two user actions that protect the product (dry before docking; press the tab to release) on the quick-start card | Design; Owner | Manual proof | Not started | REPO: `mechanical/README.md` section 7; `docs/research/power.md` risk 4; `DESIGN_SPEC.md` section 6 (E13). General duty: PROVISIONAL |

### 2.4 State rules: California and the battery laws

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 22 | California Proposition 65 | If the product can expose a person in California to a listed chemical above the safe level, it needs a warning. Since 1 January 2025 the short form of the warning must name at least one chemical. Products made before 1 January 2028 may still carry the old short form. Small businesses are exempt (recalled as fewer than ten employees) | Collect a statement from each material supplier (nylon powder and dye, adhesives and resins, solder, cable if one is shipped). Then decide: no warning, with the statements on file; or a warning in the new form naming a chemical | Vendor document; Owner | Supplier statements; the decision | Not started | VERIFIED as law-firm and test-house summaries [C14]. The small-business threshold: PROVISIONAL |
| 23 | California SB 1215: products with a battery built in | Since 1 January 2026 California buyers pay a recycling fee on "covered battery-embedded products". The maker must send a notice to its California retailers and to the state agency CalRecycle each year by 1 July, saying which of its products are covered, and must send a yearly report from 1 July 2027 (sales, battery chemistry and more). One industry summary adds that the product must be labelled with the maker's name or brand and that the battery chemistry must be on the label or on the maker's website. A marker whose cell cannot be removed with ordinary tools looks like such a product | Read the definition and confirm the GL-1 is covered. If so: yearly notice, yearly report, name or brand on the product, chemistry on the label or website. Tell any California retailer | Owner | Notice and report copies; label artwork | Not started | VERIFIED [C15] (CalRecycle page as extracted; the labelling detail comes from one industry article). The fee amount: **not found**. Whether the GL-1 meets the definition: PROVISIONAL |
| 24 | Other states' battery laws | Several states now have battery "stewardship" laws: the maker joins and pays into a collection scheme. Illinois' programme started on 1 January 2026; Washington has adopted its final rule, which includes labelling; Colorado's labelling duty starts on 1 July 2029. Most of these laws exempt products whose battery is built in, or only study them, but that is changing | Keep a watch list. Check again before the first sale and once a year | Owner | Dated note in the file | Not started | VERIFIED as law-firm and trade-press summaries [C16]. Details for each state: PROVISIONAL |
| 25 | Federal battery labelling | The 1996 federal Battery Act sets labels and easy-removal rules for nickel-cadmium and certain small sealed lead-acid batteries. Nothing was seen that extends it to lithium-ion | No federal chemistry label is required, on our reading. PROPOSED good practice: mark "Li-ion" and a "do not put in the trash" symbol on the packaging, and give disposal advice in the manual | Design | Artwork | Not started | VERIFIED [C17] for what the Act covers. That lithium-ion is outside it: **PROVISIONAL** (not addressed in what was seen) |
| 26 | Fluoropolymer vent (PFAS) | The pressure vent is a fluoropolymer membrane (ePTFE). Some states have passed laws on "PFAS in products" with broad definitions that can include fluoropolymers, with reporting duties and future bans | Not researched on 2026-11-11, and not since. Ask the vent maker for its statement. Check the state laws before the first sale | Vendor document; Owner | Maker's statement | Not started | **PROVISIONAL** (from memory; no source seen on 2026-11-11) |

### 2.5 Light from the LEDs

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 27 | LED eye safety (IEC 62471) | IEC 62471 is the international standard for the "photobiological safety" of lamps, and LEDs are judged as lamps under it. It sorts sources into four risk groups; the lowest, RG0, is called "exempt". The GL-1 has 16 small LEDs (red, about 631 nm; infrared, about 850 nm) that face the grass, sit behind clear resin, and light one at a time, briefly, during a read. The grain reading is off by default, but **the user can switch it on in the settings**, and then all 16 LEDs are cycled during each tilt read. So the assessment must assume that the LEDs can light in the user's hands. With the resistors in the specification each LED runs at about 6 mA (red) and about 10 mA (infrared), far below its rating; this file uses the higher figure, 10 mA, at which the infrared output is of the order of 1 milliwatt per steradian. We expect the exempt group. Since E3 the infrared part is the ams OSRAM SFH 4053B, which replaces the SFH 4053; the red part is the Vishay VLMS1500-GS08. The data sheet of the SFH 4053B has not been read (its wavelength is 850 nm in some search extracts and 860 nm in others), so the output figure above belongs to the earlier part and is PROVISIONAL for this one. No US federal rule requires this assessment for LEDs; retailers and other countries may ask for it. No laser is used, so the federal laser rules do not come in | A short written assessment to IEC 62471: the two LED data sheets, the drive current, the duty, the worst case of someone turning the marker over and looking into the opening from 100 to 200 mm. Ask each LED maker for its own statement. Keep lasers and laser-type emitters (VCSELs) out of later revisions | Design; Vendor document | The assessment; the makers' statements | Not started | VERIFIED [C19] for the standard's risk groups and that LEDs fall under it. The risk group of these two LEDs: **not found**. "No US rule" and the laser point: PROVISIONAL. LED data: REPO, `bom-verification-opto.md` 3.6 and 3.7 (written before E3); parts: `DESIGN_SPEC.md` section 4 (E3); `docs/SOURCING.md` section 12, A9. LED current: REPO, `firmware/README.md` "Drivers" (note "Grain LED current"). The user setting: REPO, `firmware/README.md` "Settings" and `firmware/core/gl_settings.h` (grain: 0 = off, the factory default; 1 = on) |

### 2.6 Materials

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 28 | RoHS and REACH | Not US federal law. Retailers and marketplaces commonly ask for a RoHS declaration, and both are required for sale in the EU and UK. **What the parts support:** the processor (STM32U585RIT6) is listed by its maker as RoHS compliant ("ECOPACK2"). The other parts were not checked on 2026-11-11, and have not been since. Mainstream chips, the display, the cameras and the connectors normally come with a maker's declaration, but "normally" is not evidence. The items most likely to need work are the ones without a part number yet: the nine adhesive classes in which no product is chosen, the dyed nylon, the watch crystal, the ball feet, the cell. **In the design (rev E):** the gap "lead-free assembly is not stated" is closed by E5: the specification and the fabrication notes of both boards say lead-free (SAC305) assembly with RoHS-compliant parts. That is an instruction to the assembler, not a declaration from any part maker | Collect a RoHS declaration and a REACH statement (substances of very high concern) for every line of the parts list, including each adhesive once chosen. Repeat "lead-free assembly, RoHS-compliant parts" on the board order (it is in the fabrication notes). Build one table: part, declaration on file, date | Vendor document; Design | The table and the declarations | Not started | VERIFIED [C20] for the processor only. Everything else: **PROVISIONAL** or not checked. Lead-free: REPO, `DESIGN_SPEC.md` section 4 (E5); `electrical/gl1_main/out/fab/README.txt` and `electrical/gl1_cradle/out/fab/README.txt`. Adhesives: `docs/SOURCING.md` section 7. Country of manufacture for most parts: not found (`docs/SOURCING.md` section 11, item 22) |

### 2.7 What may be claimed

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 29 | Origin claims ("Made in USA") | The FTC's Made in USA Labeling Rule (16 CFR Part 323, in force since 13 August 2021) allows an unqualified "Made in USA" label only when the product is "all or virtually all" made in the United States: final assembly here, and no more than negligible foreign content. The same standard reaches "Manufactured in USA", "Built in USA" and claims that are implied. Advertising outside the label is policed under the FTC's general power against deception. Where the GL-1's parts are made is not known for almost every line, and none is known to be made in the US (`docs/SOURCING.md` section 1.4 and section 11, item 22). **"US-sourced" in this project means "bought from a US seller and shipped from the US". It says nothing about where a part was made.** | **May not be claimed:** "Made in USA", "American made", "US-made parts", or a flag or map that suggests it. **Do not use "US-sourced" in public at all:** a buyer will read it as "US-made". **May be claimed, if true and documented:** a qualified statement that names the limits, for example "Assembled in the USA from imported parts". Write "from imported and US parts" only once the origin table shows which parts are made in the US: at revision E of the sourcing report the country of manufacture is recorded for three of its 86 lines (the cell, reported as China and unverified; the vent and the trial film, Germany), and none is the US (`docs/SOURCING.md` section 1.4). Even "Assembled in USA" has conditions. As law firms summarise the FTC's guidance (reported in review): the principal assembly and the last substantial transformation must take place in the US, and the US work must be substantial. So before any assembly claim, get it **in writing** that the board assembly and the printing are done in the US: one assembler named in the sourcing report also uses partner factories abroad, and three print bureaus pass orders to partner shops (`docs/SOURCING.md` section 8). Have the final wording reviewed. Keep an origin table for every part and the invoices of the board assembler and print bureau | Owner; Attorney for the final wording | Origin table; written confirmation of the US build sites; invoices; the reviewed wording | Not started | VERIFIED [C21] for the rule, the "all or virtually all" standard and its reach. The conditions for "Assembled in USA" (reported in review [C29], not re-opened) and the example wording: **PROVISIONAL** (the FTC guidance page was not opened) |
| 30 | Performance claims | An advertising claim must be true and backed by evidence at the time it is made. Every performance number in this project is a simulation on synthetic greens, with decisive inputs nobody has measured | No holing percentages, no "reads greens like a tour player", no accuracy figures in public until the field tests of `VALIDATION_PLAN.md` section 2.5 have produced them | Owner | The test reports behind each claim | Not started | PROVISIONAL (general principle, not searched on 2026-11-11). REPO: `sim/results/REPORT.md` section 13 |
| 31 | Water and footstep claims | The same principle. The design is glued and vented; the honest claim to earn is "rain and wet grass". An "IP" code (for example IPX7: 1 m of water for 30 minutes) may only be printed with a test report to the standard IEC 60529. EVT units are declared not step-proof | Say nothing about water or footsteps until the tests in `VALIDATION_PLAN.md` sections 2.10 and 2.11 are passed on the production design. If an IP code is wanted, a lab test | Owner; Test lab | Test reports | Not started | VERIFIED [C28] for what IPX7 means. REPO: `mechanical/README.md` sections 9 and 12 |

### 2.8 The Rules of Golf

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 32 | Rule 4.3 and the "alignment device" definition | Rule 4.3a allows a player to get distance and direction information. It does not allow measuring elevation changes, or having a device interpret the information, for example to recommend a line of play. The Equipment Rules add: an object made to mark the spot of a ball is an "alignment device" if it "incorporates features designed to measure, gauge or interpret slope, green speed or other conditions, or includes optical or electronic components" (in force since 1 January 2020). Size does not matter for that clause. Using such a device in a way that creates a potential advantage is a breach of Rule 4.3: the general penalty the first time, disqualification the second. **Our reading (PROVISIONAL): the GL-1 does every one of these things, so none of its functions may be used in a round played under the Rules of Golf, and no firmware mode changes that.** One point is not settled by anything seen: whether such an object may still serve as a plain ball marker when its functions are not used. The sources show that the GL-1 is an "alignment device" because it contains electronics, and that using it to help is a breach. They do not say that merely marking the spot with it is one. For this design the question hardly arises: the GL-1 has no off switch, wakes when it is moved and takes a read by itself. So no "allowed if switched off" claim may be made. No amendment of revision E changes this reading: the functions added or reworded by E29 to E33 (the survey, the recall of a result, the display states) are all ways of showing a line | Sell it as a practice and training device, and say so on the box, the quick-start card and the first screen. Since E10 the legend artwork and page 1 of the INFO screen carry the words "PRACTICE DEVICE"; the full sentence of row 33 is not frozen in either place. Advise users to mark with a coin in any round that counts | Owner; Design (first-screen text) | Packaging and screen proofs | Not started | VERIFIED for the quoted rule texts: [C22] Rule 4 page and the R&A's page on distance-measuring devices; [C23] the USGA Equipment Rules page with the definition. The conclusion in bold is our reading: **PROVISIONAL**. Reported in review [C29], not re-opened: the governing bodies' notice to ball-marker makers of 13 December 2019 says alignment devices "may not be used by the player in a specific manner", and a published clarification (4.3a/1) describes the breach as setting the device down to show the line and positioning the ball from it. Rule 14.1a and Rule 10.2b (lifting the marker; setting an object down to show the line), cited in the earlier research: PROVISIONAL |
| 33 | The exact wording, and its risks | Wording drafted by the earlier research: **"For practice and training. Not permitted during a round played under the Rules of Golf (Rule 4.3)."** Risks: (a) Words such as "legal", "conforming", "approved", "tournament mode", or the names or marks of the USGA or The R&A, would be a false claim and a trademark problem. (b) "Stipulated round" is the older term; the current Rules are recalled as saying simply "round". Use the current term. (c) Do not say or hint that the marker is fine in a round "if the screen is off" or "if only used to mark the ball". Nothing seen settles that question (row 32), the marker cannot be switched off, and only a written decision from the USGA or The R&A could support any such statement. None exists. (d) Posting scores: advise users not to post, for handicap, a round in which the device was used | Freeze the wording only after someone has read the current Rule 4.3, its clarifications and the Equipment Rules definition on the official pages. Consider asking the USGA's equipment standards staff to look at the packaging text | Owner | The page print-outs with the date read; any reply from the USGA | Not started | The draft wording: REPO, `docs/research/rules-compliance.md` 2.1 (unverified there). Points (b) and (d): **PROVISIONAL** |

### 2.9 Other people's rights: patents and trademarks

| # | Topic | What applies and why | What must be done | By whom | Evidence needed | Status | Source |
|---|---|---|---|---|---|---|---|
| 34 | Patents | **No freedom-to-operate search has been done.** The earlier research listed four US patent numbers on electronic ball markers by title only. Nobody on this project has read their claims, checked who owns them or whether they are in force. **This checklist does not assess any patent, and no file in the repository does.** | A freedom-to-operate search and opinion by a registered patent attorney **before any sale, pre-order or public launch**. Give them the specification and the list of functions: tilt sensing in a ball marker, stereo cameras ranging a flagstick, an aim line on a display, the grain sensor, the half-turn re-read, the cradle | Attorney | Written opinion | Not started | REPO: `docs/research/rules-compliance.md` section 5, row 30 ("numbers, owners, claims and status not checked by either pass") |
| 35 | Trademarks | **No trademark search has been done** for the product name, the model name or any logo. Names of others must not be used in a way that suggests endorsement (the golf bodies, and product names such as the green-speed ramp's) | A clearance search before the name is printed on anything, then a decision whether to register | Attorney; Owner | Search report | Not started | PROVISIONAL (general practice) |
| 36 | Software licences | The firmware will include the chip maker's driver library and a USB library. Each comes with licence terms. The small 5 x 7 font on the display is the project's own: it is drawn in the project's generator script, so it needs no licence | List every third-party piece and its licence before release | Design | The list | Not started | REPO: `firmware/README.md` "What is not done" (the libraries are not yet in the build); `firmware/core/gl_font_data.c` (header: "GENERATED by tools/gen_font.py"). Licence terms of the two libraries: not checked |

---

## 3. A short second list: what changes outside the US

Not researched in depth. One line per difference, so that nobody assumes the US file is
enough. Everything here needs its own check before a sale in that market.

### Canada

| Topic | What changes | Status | Source |
|---|---|---|---|
| Radio interference | Canada's standard for this kind of equipment is ICES-003 (Issue 7). No certification: the maker tests, keeps the report and self-declares. The product carries the two-language label "CAN ICES-003(B) / NMB-003(B)". Ask the US lab beforehand to write its report so that it also serves Canada | Not started | VERIFIED as lab summaries and the regulator's page [C24]; label placement rules not seen; whether one test session serves both: PROVISIONAL |
| Language | Packaging, manual and warnings in English and French | Not started | PROVISIONAL |
| Battery transport, product safety reporting | Canada has its own dangerous-goods rules and its own consumer product safety act with a duty to report incidents | Not started | PROVISIONAL |

### United Kingdom

| Topic | What changes | Status | Source |
|---|---|---|---|
| Product marking | Great Britain has its own "UKCA" mark, but the government announced on 1 August 2023 that the European "CE" mark stays accepted indefinitely for the product rules it listed (18 at first, more added in 2024). Whether the electromagnetic-compatibility and RoHS rules are on that list was not shown in what was seen | Not started | VERIFIED [C25] for the announcement; the list: PROVISIONAL |
| The rest | UK versions of the EU rules below (interference, hazardous substances, waste electronics, batteries, general product safety), a UK address on the product, and producer registration for batteries and waste electronics | Not started | PROVISIONAL |
| Rules of Golf | The same Rules apply worldwide. The practice-device statement is unchanged | - | VERIFIED [C22] (The R&A publishes the same Rule 4.3) |

### European Union

| Topic | What changes | Status | Source |
|---|---|---|---|
| **Battery must be removable (the big one)** | Under the EU Batteries Regulation (2023/1542), Article 11, from **18 February 2027** a portable battery in a product must be readily removable and replaceable by the end user with commonly available tools. The GL-1's cell is soldered in and the housing is glued shut for good. There are exceptions (for some appliances used in wet conditions, where a professional may do the replacement). On 14 July 2026 the Commission adopted a further act that would add product categories; reported in review, it was still under scrutiny by the Parliament and the Council and not yet in force. Whether a golf marker fits any category was not established. And an exception only changes **who** replaces the battery (a professional instead of the user). None seen allows a product whose cell nobody can replace, which is the GL-1's case. **As designed, the GL-1 is unlikely to be sellable in the EU after that date.** | Not started | VERIFIED [C26] for the rule, the date and the existence of exceptions. The status of the July 2026 act (reported in review [C29], not re-opened) and our reading of what an exception allows: **PROVISIONAL**. Fit to the GL-1: PROVISIONAL |
| Battery labels | The same regulation phases in labels: the crossed-out bin symbol (from 18 August 2025), a general information label (from 18 August 2026 or later, depending on a detailed act), a QR code (from 18 February 2027) | Not started | VERIFIED as a compliance firm's timeline [C26]; sources disagree on whether dates have moved |
| CE marking | CE mark and an EU declaration of conformity under the electromagnetic compatibility directive (2014/30/EU) and RoHS (2011/65/EU). The US emissions report does not cover the EU's immunity tests | Not started | PROVISIONAL |
| General product safety | The General Product Safety Regulation (2023/988) applies since 13 December 2024. A product from outside the EU must have a "responsible person" established in the EU, named on the product or its packaging | Not started | VERIFIED as the Commission's material and law-firm summaries [C27] |
| Waste, chemicals, packaging | Registration as a producer of waste electronics and batteries in each country of sale; REACH disclosure of substances of very high concern; packaging rules; manuals in each national language | Not started | PROVISIONAL |
| LED safety | The IEC 62471 file of row 27 is expected here | Not started | PROVISIONAL |

---

## 4. Design and document items this checklist raises

Revision 2 of this checklist listed 14 items against the revision D design. The amendments
have since dealt with some of them. A building inspector's list works the same way: an item is
struck off when the drawing shows the fix, and it comes back for a second visit when the wall
is built. Every "closed" below is closed **on paper only**.

### 4.1 Closed in the design at revision E (not built, not tested)

| Old item | Gap at revision D | What revision E carries | What still stands |
|---|---|---|---|
| 1 | No place for regulatory marks | E10 and E18: a legend on the underside of the base plate with two statement blocks (88 characters together by `mechanical/README.md`, 88 each by the specification's wording: contradicted, `docs/RELEASE_GATES.md` G-045) and a serial-number box; an INFO screen in the firmware with 4 text pages. `mechanical/README.md` section 4, item 9; `firmware/README.md` "The regulatory and information screen" | The text in both places is a placeholder. Which route carries the FCC statement is not decided (row 5). The legend print rules are assumptions until a fabricator quotes |
| 2 | The cradle's USB-C resistors and fuse rating were not in the design | E6: two 5.1 kilohm resistors, a resettable fuse and a static-discharge clamp, in the specification and on the routed cradle board. `electrical/gl1_cradle/out/spec_rules.md` | The fuse trips at 0.75 A where the first proposal said about 0.5 A; its ratings are listing data, PROVISIONAL (row 15) |
| 3 | No ship mode | E13: ship mode in the specification and in the firmware source, exercised on the simulator. `firmware/README.md` "Cradle, ship mode and the hot cell" | Its current misses the requirement in the model: 12.9 against 5 microamps (item 4.3, 1). The transport rule it answers is PROVISIONAL (row 12) |
| 4 | Two charger-supervision gaps (USB loader running; firmware hung) | E1: a charger chip with its own temperature sensor, which does not need the processor. `DESIGN_SPEC.md` section 4 | With no firmware the limit is the chip's own window, not 0 to 45 C; thresholds PROVISIONAL; a broken-off sensor is not covered (row 14) |
| 6 | Lead-free assembly was not stated | E5: lead-free (SAC305), RoHS-compliant parts, in the specification and in both boards' fabrication notes | No declaration has been collected from any part maker (row 28) |
| 7 | No serial number | A serial number derived from the processor's built-in number, stored at the factory, shown on the INFO screen and marked in the legend box. `firmware/README.md` "Calibration records"; `MANUFACTURING_PLAN.md` section 7.3 | Derived, not assigned: two units can share one. Whether that serves a recall is an owner decision (row 18) |
| 13 | A unit shipped at 30 % charge may be flat in about a month | Ship mode (E13) and a stated requirement: 5 microamps, 3 months from 30 % (E23, PROPOSED) | The model gives 42 days in ship mode and 23 days asleep, from 30 %. Not closed (rows 11 and 12) |

The thermal limit added by E13 (no camera read when the cell reads above 60 C) answers no
item of revision 2. It is recorded here because it belongs in the user guide (row 21).

### 4.2 Still open, carried from revision 2

Numbers are those of revision 2.

5. **No safety certificate for the cell has been seen**, and the cell has one US seller.
   `docs/SOURCING.md` 9.3. Rows 9 and 13.
8. **The sealed, soldered cell blocks EU sales from February 2027.** An exception would only
   let a professional replace the cell instead of the user; none seen covers a cell that
   nobody can replace (our reading, PROVISIONAL). `DESIGN_SPEC.md` sections 3 and 5. Section 3.
9. **USB vendor and product numbers do not exist.** The firmware holds placeholders and its
   release check refuses a release build (E34). `firmware/README.md` "Boot stub (E34)". Row 16.
10. **The earlier research is out of date on the radio.** `docs/research/rules-compliance.md`
    section 2.2 still budgets a Bluetooth listing and a "Contains FCC ID" label. Neither
    applies: the design has had no radio since revision D. The file should carry a note
    pointing here.
11. **The grain LED current is lower than the research assumed**: about 6 mA (red) and 10 mA
    (infrared) against 20 mA (E3). Good for row 27, which uses the higher figure; a question
    for the grain sensor (`VALIDATION_PLAN.md` section 7).
12. **The user can switch the grain LEDs on.** "Ships disabled" is a factory default, not a
    lock: GRAIN is an item of the settings dial (`firmware/core/gl_settings.h`). Decide
    whether shipped firmware should hide that setting until the sensor has passed its gates.
    Row 27.
14. **Nothing yet shows where the product is assembled.** Before any "Assembled in USA"
    wording, the board assembler and the print bureaus must confirm their US build sites in
    writing (`docs/SOURCING.md` section 8). No quote has been requested from any of them.
    Row 29.

### 4.3 New at revision E

1. **Ship mode misses its own requirement in the model.** 12.9 microamps plus the display
   panel (no figure known) against 5; 42 days from a 30 % charge against 3 months. The
   firmware notes say that 3.3 of the 12.9 microamps are in the firmware's hands and the rest
   is the board. `firmware/README.md` "Cradle, ship mode and the hot cell". Rows 11 and 12.
2. **The regulatory text is a placeholder in two places**, the legend artwork and
   `firmware/app/gl_regulatory.h`. This checklist is named as the source of that text, and it
   cannot supply it: the wording of rows 5, 6 and 33 is PROVISIONAL until someone reads the
   regulation and the Rules on the official pages. Freezing the text is a gate before the
   base plates are ordered and before any release build.
3. **With no firmware running, the cell may be charged up to the charger chip's own upper
   limit**, taken as 60 C in the model, not 45 C. Whether that is acceptable depends on the
   cell data sheet, which has not been seen. Row 14.
4. **The infrared LED changed (E3) and its data sheet is unread.** The eye-safety file of row
   27 must be written for the SFH 4053B.
5. **A new marker does nothing until it is docked once**, because it leaves the factory in
   ship mode. The quick-start card and the box must say so. Rows 12 and 21.
6. **No adhesive is selected in any of nine classes**, so no RoHS, REACH or Proposition 65
   statement can be collected for them yet. `docs/SOURCING.md` section 7. Rows 22 and 28.
7. **The battery-life and drop requirements of E23 are PROPOSED**, not measured. No public
   claim may rest on them (row 30).
8. **The legend's two blocks are small, and the files disagree on how small.** `mechanical/README.md`
   (section 4 item 9: "four lines of eleven each"; section 12: 88 "between them") gives 88
   characters for the two blocks together. `DESIGN_SPEC.md` E18 and the YAML comment say each
   block holds 88. Revision 3 of this checklist first copied "88 each"; the capacity is to be
   counted on drawing GL1-011 (`docs/RELEASE_GATES.md` G-045). Whatever statements are required
   (FCC, battery, the practice-device sentence, the maker's name and address) must be shared
   out between the legend, the INFO screen, the user guide and the packaging. Row 5.

---

## 5. Draft order of work (PROPOSED)

```
 NOW (costs nothing)            BEFORE ORDERING CELLS         AT EVT                    BEFORE FIRST SALE
 --------------------           ----------------------        ---------------------     ---------------------------
 Name the responsible party     UN 38.3 test summary          Emissions pre-scan        Formal FCC test, SDoC file
 Start the origin table         Cell safety certificate       Charger tests J1-J6, J10  Manual and box texts frozen
 Ask the CPSC about row 20      Cell data sheet               LED assessment            Patent FTO opinion
 Book the patent attorney       RoHS / REACH declarations     Ship-mode current         Trademark clearance
 Decide the label route (row 5) Adhesive declarations         Charge setting at packing California notices
 Freeze legend and INFO text    (after adhesives are chosen)  USB sources and short     Reporting procedure (row 18)
 (before base plates are ordered)                             (test J9)                 USB vendor and product ID
```

The patent search is in the first column on purpose. It is the one item that can stop the
product outright, and it does not depend on any hardware.

Two entries of revision 2 are gone from the "AT EVT" column because revision E carries them
on paper: "Ship mode in firmware" (E13) and "Marking area designed" (E10). What is left of
each is in the table: measuring the ship-mode current, and freezing the text.

---

## 6. What could not be verified on 2026-11-11

Revision 3 did not look at any of these again. All of them stand.

1. The full text of any regulation. Regulator sites could not be opened from this session;
   only search extracts were seen. Hosts to allow in the session's network settings for a
   proper check: `www.ecfr.gov`, `www.law.cornell.edu`, `www.fcc.gov`, `www.cpsc.gov`,
   `www.phmsa.dot.gov`, `www.iata.org`, `www.ftc.gov`, `calrecycle.ca.gov`, `oehha.ca.gov`,
   `www.usga.org`, `www.randa.org`, `eur-lex.europa.eu`, `www.energy.gov`.
2. The exact current wording of the three FCC user texts (rows 5 and 6), and the frequency
   range and limits of the emissions test (row 2).
3. Whether an SDoC test must now be done by an accredited lab, and from what date (row 4).
4. The packing details for the lithium battery mark, the exact words of its exception with
   the "two packages" condition (row 10: reported in review, not re-opened), and the airline
   rule on accidental activation (row 12).
5. Whether the federal battery-charger standard is still in force, and whether it and the
   California charger rules cover this product (row 17).
6. Any CPSC statement on pouch cells under Reese's Law (row 20).
7. The definition of a "covered battery-embedded product" and the fee (row 23); the state
   laws on PFAS (row 26).
8. The risk group of the two LED types (row 27).
9. RoHS and REACH status of every part except the processor (row 28).
10. The FTC's conditions for "Assembled in USA" (row 29).
11. The current wording of Rules 4.3, 10.2b and 14.1a, and whether the Equipment Rules page
    seen is the latest version (rows 32 and 33).
12. Everything in section 3 beyond the lines marked VERIFIED.
13. Everything worded "reported in review" [C29]: the words of the battery-mark exception
    (row 10), the conditions for "Assembled in USA" (row 29), the governing bodies' 2019
    notice to ball-marker makers and the clarification on alignment devices (row 32), and the
    status of the EU act of July 2026 (section 3). This revision could not search or open
    pages. Extra hosts to allow: `digital-pd.usopen.com`, `products.cooley.com`,
    `www.dorsey.com`.

---

## 7. Sources

Seen on 2026-11-11 as text returned by a web search. "VERIFIED" in the tables refers to these.

| Ref | Source | Used for |
|---|---|---|
| C1 | eCFR, 47 CFR 15.101. https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-B/section-15.101 ; mirror with the personal-computer row: https://www.customsmobile.com/regulations/expand/title47_chapterI_part15_subpartB_section15.101 | Authorization table: SDoC or certification |
| C2 | eCFR, 47 CFR 2.1077. https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-2/subpart-J/subject-group-ECFR64d0de5de218f0c/section-2.1077 | Compliance information; responsible party in the US |
| C3 | eCFR, 47 CFR 15.19. https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-A/section-15.19 | Label statement; small-device paragraph |
| C4 | eCFR, 47 CFR 15.105 and 15.21. https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-B/section-15.105 ; https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-A/section-15.21 | Class B notice; modification caution |
| C5 | Federal Register, 7 August 2025, document 2025-14970. https://www.federalregister.gov/documents/2025/08/07/2025-14970/promoting-the-integrity-and-security-of-telecommunications-certification-bodies-measurement ; Inside Global Tech, 30 October 2026. https://www.insideglobaltech.com/2026/10/30/fcc-adopts-new-rules-limiting-the-use-of-certain-foreign-test-labs-in-equipment-authorizations/ ; DLA Piper, October 2026. https://www.dlapiper.com/en/insights/publications/2026/10/fcc-to-vote-on-limiting-equipment-authorization-testing | Test-lab rules of 2025 and 2026 |
| C6 | US DOT PHMSA, lithium battery test summary brochure and 2024 guide. https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/2022-01/Test%20Summary%20Brochure%20web.pdf ; https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/2024-09/Lithium-Battery-Test-Summary-2024.pdf | UN 38.3 test summary duty |
| C7 | 49 CFR 173.185 (as mirrored) and PHMSA interpretation letters. https://www.law.cornell.edu/cfr/text/49/173.185 ; https://www.phmsa.dot.gov/regulations/title49/interp/25-0021 ; https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/docs/standards-rulemaking/hazmat/interpretations/75371/210050.pdf | 20 Wh small-cell limit; mark not needed for few cells in equipment |
| C8 | Lion Technology, "Cheat Sheet 012: Lithium SOC 2026". https://www.lion.com/getmedia/34a1639d-f193-4c04-90b2-acc50fb051af/Cheat-Sheet-012-Lithium_SOC_2026.pdf ; IATA lithium battery guidance document (contents only). https://www.iata.org/contentassets/05e6d8742b0047259bf3a700bc9d42b9/lithium-battery-guidance-document.pdf | 30 % charge: recommended for cells in equipment |
| C9 | Element, lithium-ion battery certification. https://www.element.com/resources/articles/lithium-ion-battery-certification ; In Compliance Magazine on UL 62133. https://incompliancemag.com/ul-62133-a-globally-harmonized-option-for-portable-battery-compliance/ ; Compliance Gate on UL standards. https://www.compliancegate.com/ul-standards/ | Which cell and pack standards exist; marketplace demands |
| C10 | Infineon knowledge base, USB Type-C termination resistors. https://community.infineon.com/t5/Knowledge-Base-Articles/Termination-Resistors-Required-for-the-USB-Type-C-Connector/ta-p/253544 ; Microchip, Type-C CC signals. https://developerhelp.microchip.com/xwiki/bin/view/applications/usb/typec-features/cc-vconn-signals | 5.1 kilohm pull-downs on both CC pins |
| C11 | CPSC, duty to report. https://www.cpsc.gov/node/24235 ; 16 CFR 1115.12 as mirrored. https://www.law.cornell.edu/cfr/text/16/1115.12 | 24-hour reporting duty |
| C12 | CPSC, General Certificate of Conformity FAQ. https://www.cpsc.gov/FAQ/GCC ; Federal Register, certificates of compliance (eFiling). https://www.federalregister.gov/documents/2025/01/08/2024-30826/certificates-of-compliance | When a certificate is needed; filing date 8 July 2026 |
| C13 | CPSC, button cell and coin battery business guidance and FAQ. https://www.cpsc.gov/Business--Manufacturing/Business-Education/Business-Guidance/Button-Cell-and-Coin-Battery ; https://www.cpsc.gov/FAQ/Button-Cell-and-Coin-Battery-FAQs ; Federal Register, 21 September 2023. https://www.govinfo.gov/content/pkg/FR-2023-09-21/html/2023-20333.htm | Definition of a button cell or coin battery |
| C14 | Sidley, February 2025. https://www.sidley.com/en/insights/newsupdates/2025/02/new-changes-to-californias-proposition-65-shortform-warning-labels ; UL Solutions. https://www.ul.com/news/chemicals-usa-california-proposition-65-amends-short-form-warning-methods-and-content ; Foley, April 2025. https://www.foley.com/insights/publications/2025/04/prop-65-changes-to-short-form-warnings-will-cause-long-term-impacts/ | Prop 65 short-form changes and dates |
| C15 | CalRecycle, SB 1215 covered battery-embedded products. https://calrecycle.ca.gov/electronics/embeddedbatteries/ ; Auto Care Association, June 2026. https://www.autocare.org/news/blog/advocacy-in-action/post/aina/2026/06/12/california-sb-1215-is-in-effect--what-you-need-to-do-now | Fee start, notices, reports, labelling |
| C16 | DLA Piper, June 2026. https://www.dlapiper.com/en/insights/publications/2026/06/lithium-batteries-emerging-risks ; Resource Recycling, October 2026. https://resource-recycling.com/policy-now/2026/10/13/eprs-next-fight-is-over-embedded-batteries/ | State battery stewardship laws |
| C17 | Public Law 104-142 (the 1996 Battery Act). https://www.govinfo.gov/content/pkg/PLAW-104publ142/html/PLAW-104publ142.htm ; EPA white paper on battery labelling, January 2025. https://19january2025snapshot.epa.gov/system/files/documents/2025-01/battery-labeling-requirements-and-standards-white-paper.pdf | What the federal Act covers |
| C18 | DOE, battery chargers final rule, 2016. https://www.energy.gov/sites/prod/files/2016/05/f31/Battery%20Chargers%20Final%20Rule.pdf ; Federal Register, 16 May 2025, proposed rescission. https://www.govinfo.gov/content/pkg/FR-2025-05-16/html/2025-08598.htm | Federal charger standard and the proposal to cancel it |
| C19 | ams OSRAM application note, photobiological safety of LED light sources. https://look.ams-osram.com/m/1d720a7b18ab3fce/original/Details-on-photobiological-safety-of-LED-light-sources.pdf ; LEDs Magazine. https://www.ledsmagazine.com/smart-lighting-iot/smart-cities/article/16695465/led-based-products-must-meet-photobiological-safety-standards-part-3-magazine | IEC 62471 risk groups; LEDs treated as lamps |
| C20 | STMicroelectronics eStore, STM32U585RIT6. https://estore.st.com/en/stm32u585rit6-cpn.html | RoHS status of the processor |
| C21 | FTC, Made in USA Labeling Rule. https://www.ftc.gov/made-in-usa-rule ; FTC, Complying with the Made in USA Standard. https://www.ftc.gov/business-guidance/resources/complying-made-usa-standard ; Kelley Drye, 2024. https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/ftc-updates-made-in-the-usa-guidance | "All or virtually all"; reach of the standard |
| C22 | The R&A, Rules of Golf, Rule 4. https://www.randa.org/sw/rog/the-rules-of-golf/rule-4 ; The R&A, distance-measuring devices. https://www.randa.org/players-rule-finder/players-rule-finder/equipment/other-equipment/distance-measuring-devices | Rule 4.3a allowed and not allowed; penalties |
| C23 | USGA, Equipment Rules, Part 6 (page "part-6-rule-8"). https://www.usga.org/equipment-standards/equipment-rules-2019/equipment-rules/part-6-rule-8.html ; The R&A, Rules of Equipment, Part 6. https://www.randa.org/roe/the-rules-of-equipment/part-6-devices-and-other-equipment | Definition of an alignment device for ball markers |
| C24 | ISED Canada, interference-causing equipment standards. https://ised-isde.canada.ca/site/certification-engineering-bureau/en/node/88 ; Element, ICES-003 Issue 7. https://element.com/nucleus/2021/ices-003-issue-7-standard-updates | Canadian self-declaration and label |
| C25 | UK government press release, 1 August 2023. https://www.gov.uk/government/news/uk-government-announces-extension-of-ce-mark-recognition-for-businesses. ; US Department of Commerce market note. https://www.trade.gov/market-intelligence/united-kingdom-extends-ce-mark-recognition | CE mark accepted indefinitely in Great Britain |
| C26 | European Commission notice C/2025/214 (guidance on battery removability). https://eur-lex.europa.eu/eli/C/2025/214/oj/eng ; TUV SUD on Article 11. https://www.tuvsud.com/en-gb/resource-centre/blogs/uk/testing-and-certification-blog/eu-battery-regulation-2027-article-11 ; REACH24H on the July 2026 delegated act. https://en.reach24h.com/news/industry-news/sustainability/eu-portable-battery-removability-exemptions-2026 ; Compliance Gate timeline. https://www.compliancegate.com/eu-batteries-regulation-timeline-and-dates/ | EU battery removability and label dates |
| C27 | European Commission, GPSR questions and answers. https://webgate.ec.europa.eu/safety/consumers/consumers_safety_gate/obligationsForBusinesses/documents/Q&A.pdf ; Baker McKenzie, November 2025. https://www.bakermckenzie.com/en/insight/publications/resources/product-risk-radar-articles/general-product-safety-regulation | EU general product safety; responsible person |
| C28 | Wikipedia "IP code" as mirrored in the search results. https://www.wikipedia.org/wiki/IP67 | Meaning of IPX7 |
| C29 | **Reported by the second review; not opened by this revision (PROVISIONAL).** PHMSA interpretation letter. https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/docs/standards-rulemaking/hazmat/interpretations/70676/180142.pdf ; Dorsey on "Assembled in the USA". https://www.dorsey.com/intellectual-property/blog-the-tmca/assembled-in-the-usa-the-ftc-confirms-whats-required ; USGA and The R&A, notice to ball-marker manufacturers, 13 December 2019. https://digital-pd.usopen.com/content/dam/usga/pdf/Equipment/Notice%20to%20Ball-Marker%20Manufacturers%20(Final%20Announcement).pdf ; USGA, Clarifications of the 2019 Rules of Golf, October 2022. https://www.usga.org/content/dam/usga/pdf/2022/rules/Clarifications%20of%20the%202019%20Rules%20of%20Golf%20-%20October%202022.pdf ; Cooley on the EU battery removability exemptions, May 2026. https://products.cooley.com/2026/05/15/eu-batteries-regulation-european-commission-proposes-new-exemptions-from-end-user-battery-removability-requirements/ | Row 10 (words of the mark exception); row 29 (assembly claim); row 32 (how alignment devices may be used); section 3 (status of the EU act) |

---

## 8. Glossary of the papers this checklist asks for

| Paper | Who writes it | One-line description |
|---|---|---|
| Emissions test report | Test lab | Measured radio noise of the marker and cradle against the Class B limits |
| SDoC compliance information | Owner | The short statement in the manual naming the product and the US responsible party |
| UN 38.3 test summary | Cell maker | Says the cell type passed the transport abuse tests |
| IEC or UL 62133-2 report, or UL 1642 certificate | Cell maker, or a lab | Says the cell (and pack) passed the safety tests for portable use |
| RoHS declaration, REACH statement | Each part and material maker | Says which restricted or listed substances the part contains |
| Prop 65 supplier statement | Each material maker | Says whether a California-listed chemical is present |
| IEC 62471 assessment | Design, with the LED makers' data | Shows the LEDs are in the lowest risk group |
| Origin table | Owner | For each part: where it was made, with the evidence |
| FTO opinion | Patent attorney | Says whether the product can be sold without infringing patents in force |

---

## 9. What this checklist is not

- **It is not legal advice.** It is an engineering checklist, written to make sure nothing
  obvious is forgotten. It was not written or reviewed by a lawyer. Laws were summarised
  from search extracts and, where marked, from memory.
- **It is not complete.** It covers the topics the project asked about. It does not cover
  tax, customs and tariffs, export controls, insurance, warranty law, privacy law, marketplace
  seller policies, employment or workshop safety.
- **It is not a patent or trademark opinion.** No patent was read. No freedom-to-operate or
  trademark search has been done. One is needed before any sale.
- **It is not current for long.** Several rules named here changed in 2025 and 2026, and some
  are changing now (the FCC's test-lab rules, the federal charger standard, the state battery
  laws, the EU battery rules). Every line must be re-checked against the official text on the
  day it is acted on.
- **It is not evidence of compliance.** Nothing has been tested, collected or filed. A line
  becomes "done" only when the evidence named in its row is in the compliance file.
- **It is not a test plan a lab has agreed to.** Which tests apply, in which set-up and to
  which limits, is for an accredited test lab to confirm in writing before a test is booked.
- **"In the design" is not "done".** Where revision 3 says an amendment closed a gap, the gap
  is closed in the design files. Nothing has been built.

---

## 10. What changed in revision 3 (2026-11-20)

No search was made and no page was opened. No legal statement, date, label or source of
revision 2 was changed. Design facts were re-read from the files named in each row.

| Where | Change | Because of |
|---|---|---|
| Header, labels | Written against rev E. Two labels added: "In the design (rev E)" and "NOT MET (model)" | - |
| Section 1 | Charger, cradle and materials rows restated; rows added for ship mode and for the two places that hold statements | E1, E2, E5, E6, E10, E13, E32 |
| Row 5 | A place for the statement exists (legend, INFO screen); the text is a placeholder | E10, E18 |
| Rows 11, 12 | Ship mode exists on paper; its current misses the requirement in the model; sleep and shelf figures are those of the rev E supply model (23.7 microamps asleep, was 20.6) | E13, E23 |
| Row 14 | The two supervision gaps are closed by the charger chip's own sensor; the residual 45 to 60 C case and the PROVISIONAL thresholds are stated | E1, E2, E32 |
| Row 15 | CC resistors and fuse are in the design; the fuse figures are those of the routed cradle | E6, E25 |
| Row 16 | Placeholders and the release check named | E34 |
| Rows 18, 21 | Serial number as designed; two user-guide lines added | E10, E13 |
| Row 27 | Infrared LED part named; its data sheet is unread | E3 |
| Row 28 | Lead-free assembly is stated in the design | E5 |
| Row 29 | Origin count and section numbers follow `docs/SOURCING.md` revision 4 as edited on 2026-11-20 | - |
| Rows 32, 33 | Noted that no amendment changes the reading | E29 to E33 |
| Section 4 | Split into closed on paper (4.1), still open (4.2) and new at revision E (4.3) | - |
| Section 5 | Two EVT entries replaced by what is left of them | E10, E13 |
| References | `MANUFACTURING_PLAN.md` "gap 26" is now its section 7.4; `VALIDATION_PLAN.md` section 7 "item 9" is cited as section 7 | Both plans are now at plan revision 3 (rev E) |
| Section 1, row 5, 4.1 item 1, 4.3 item 8, section 5 (edited later on 2026-11-20, after an independent check of the documents) | The legend capacity is marked as contradicted between the mechanical notes (88 characters for the two blocks together) and the specification's wording (88 each); the chart of section 5 names charger tests J1 to J6 and J10, as row 14 does | `docs/RELEASE_GATES.md` G-045 |

