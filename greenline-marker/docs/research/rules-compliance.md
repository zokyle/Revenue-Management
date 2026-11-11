# GreenLine research: Rules of Golf status and US product regulatory compliance

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

Scope: Rule 4.3 and the Equipment Rules "alignment device" definition, FCC / ISED / Bluetooth SIG, lithium battery safety and transport, Reese's Law, LED safety, California requirements, FTC origin claims, tariffs, IP67.

## 0. Verification status (read this first)

This verification pass could not reach the web.

- Web search: all four queries attempted were refused ("web search budget is used up", a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.usga.org`, `www.randa.org`, `www.bluetooth.com` and `docs.fcc.gov` all failed to resolve. The session's cloud environment allows only package registries, MCP servers and seven unrelated website hosts, so no regulatory or rules host is reachable. No further hosts were tried, as instructed by the tool.

Consequences:

- **No rule text, regulation text, fee, date or price in this document was confirmed against a live source in this pass.** Every such item is marked UNVERIFIED. They carry forward the first report's values. The first report itself took the Rules of Golf wording from search-result excerpts, not from opened pages, because the same hosts were blocked for it.
- What was verified here: the first report's arithmetic (recomputed with a local script), its internal consistency, and its reasoning.
- Where the reviewer's own recollection (model training data, up to about mid-2026) agrees or disagrees with the report, that is stated as "reviewer recollection". Recollection is not a source and does not change an UNVERIFIED mark. Events the report dates after mid-2026 (FCC 26-73 of 29 Oct 2026, the 24 Jul 2026 Section 301 tariffs, the July 2026 FTC letters) are beyond the reviewer's recollection and could not be corroborated at all.
- This topic has no part numbers. Every candidate has MPN "n/a", so the "does the exact MPN exist / is it in stock" check does not apply. The equivalent check here is "does the rule, fee or regulation say what the report says", and that needs the primary pages.

Before any packaging text, manual text or compliance budget is frozen, a person or a follow-up session with network access must open the primary sources. Hosts that need to be allowed in the session's network settings: `www.usga.org`, `www.randa.org`, `www.bluetooth.com`, `docs.fcc.gov`, `www.fcc.gov`, `www.ecfr.gov`, `www.law.cornell.edu`, `www.cpsc.gov`, `www.federalregister.gov`, `www.phmsa.dot.gov`, `www.iata.org`, `calrecycle.ca.gov`, `www.energy.ca.gov`, `oehha.ca.gov`, `www.ftc.gov`, `ustr.gov`, `www.energy.gov`, `ised-isde.canada.ca`, `image-ppubs.uspto.gov`.

## 1. Summary

The first report's central conclusion is a negative one, and nothing found in this review weakens it: GreenLine cannot be used during a round played under the Rules of Golf, and a firmware "tournament mode" cannot be advertised as conforming without a written decision from the USGA or The R&A.

The reasoning, which matches reviewer recollection of the 2023 Rules of Golf and the Equipment Rules (UNVERIFIED in this pass):

1. Rule 4.3a(1) allows distance and direction information only. It lists as not allowed: measuring elevation changes, interpreting distance or directional information (for example a device-recommended line of play), and using an alignment device to help align the ball.
2. The Equipment Rules treat an object made to mark the spot of a ball as an alignment device if it is taller than 1.0 in, or wider than 2.0 in with line or appendage features, or if it "incorporates features designed to measure, gauge or interpret slope, green speed or other conditions, or includes optical or electronic components". The last clause applies at any size. GreenLine at dia 40-44 mm x 7 mm (1.57-1.73 in x 0.28 in, arithmetic confirmed) is inside both size limits but is caught by the electronics clause.
3. Rule 14.1a requires the ball-marker to be removed before the stroke (one penalty stroke otherwise), and Rule 10.2b bars setting an object down to show the line of play.

So the product has to be positioned and labelled as a practice and training device.

On the regulatory side the first report's US path is conventional and matches reviewer recollection of the long-standing rules: FCC Part 15 Subpart B by Supplier's Declaration of Conformity with an unmodified pre-certified BLE module; Bluetooth SIG qualification; a Li-polymer pouch cell bought with a UN 38.3 test summary and a cell safety certificate; shipment as UN3481 contained in equipment; California Prop 65, SB 1215 and battery-charger filings; a qualified origin claim; an IP67 test. All figures remain UNVERIFIED in this pass.

Changes and additions from this review:

- The US Department of Energy battery-charger standard (10 CFR 430.32(z), certification under 10 CFR 429) should be treated as applicable until shown otherwise. The first report left it as an open question. Reviewer recollection is that it covers chargers built into consumer products and powered from USB. UNVERIFIED.
- For a ball on the putting green, Rule 10.2b(2) is the more specific provision on setting an object down to show the line of play; the report cites only 10.2b(3). Reviewer recollection, UNVERIFIED.
- The lithium battery mark exception in 49 CFR 173.185(c)(3) is limited to consignments of no more than two packages (the report's excerpt was truncated at this point). Retailer or distributor shipments of more than two packages therefore need the mark on each package. Reviewer recollection, UNVERIFIED.
- The report cites the alignment-device definition as "Part 6, section 7" while the URL it gives ends in `part-6-rule-8`. The section number is unresolved; cite the section by its title until the page has been read.
- The report's cost total is arithmetically consistent with its own line items: $15.5k-23.5k for the US items, $15.8k-24.3k including Canada, rounded in the report to $16k-25k. The total excludes the patent review, any UN 38.3 retest, DOE charger testing and a USGA submission.
- The Bluetooth SIG fee ($12,000 per qualification for an Adopter member from 1 March 2026) is the largest line item and is UNVERIFIED. The previous figure the report quotes, $11,040, agrees with reviewer recollection. A variant with no Bluetooth radio would remove this fee; that is a system-architecture decision outside this topic.
- "Scores should not be posted" is a simplification. Reviewer recollection of Rules of Handicapping 2.1b is that a general-play score is unacceptable when a Rule is breached and the correct penalty is not applied, or a Rule is deliberately ignored. The practical guidance to users is unchanged: do not post rounds in which the slope or aim features were used.

## 2. Final recommendation

Status: the recommendation stands on its reasoning. No fact in it was confirmed against a live source in this pass, and none was contradicted.

### 2.1 Rules of Golf positioning

- Recommended: sell GreenLine as a practice and training device for practice greens, lessons and casual rounds that are not posted for handicap. Put the statement "For practice and training. Not permitted during a round played under the Rules of Golf (Rule 4.3)." on the box, the quick-start card and the first-boot screen. Print no USGA or R&A conformance wording anywhere.
- Fallback: implement a locked "restricted mode" in firmware (numeric distance only; tilt, elevation, break, grain, aim line and every directional graphic off; visible lock indicator). Do not call it tournament-legal. The alignment-device definition turns on the presence of electronic or optical components, not on which functions are enabled, and the cameras must face the hole to range it, which orients the marker along the line of play. A written decision from USGA Equipment Standards or The R&A is needed before any claim. The submission process, fee and turnaround are UNVERIFIED.
- Rejected: marketing the device as conforming for use in rounds.
- Guidance to users for competitions: use a plain coin.

### 2.2 Compliance checklist for a US launch

Items marked [DESIGN] constrain the hardware now. All costs and lead times are UNVERIFIED; those marked "estimate" were never sourced even by the first report.

| # | Item | Action | Cost / lead time (UNVERIFIED) |
|---|------|--------|-------------------------------|
| 1 | FCC 47 CFR Part 15 Subpart B, Class B, by SDoC | Radiated-emissions test at a US accredited lab with the BLE module installed and transmitting. Keep the test report and SDoC record. Put the 2.1077 compliance statement with a US responsible party in the manual. Mark "Contains FCC ID: (module ID)". [DESIGN: pre-certified module with its own antenna used exactly as granted; antenna keep-out; non-metal window; no second transmitter; no wireless-charging transmitter; marking area on the base and a regulatory screen in firmware.] | $1.5k-5.5k (vendor estimates of low reliability); 1-3 weeks (estimate) |
| 2 | Bluetooth SIG qualification | Qualify the end product by reference to the module's qualified design. [DESIGN: unmodified qualified stack; only features in the module's listing.] | $12,000 Adopter fee reported; days |
| 3 | Battery cell | Li-polymer pouch cell with protection circuit, bought with a UN 38.3 test summary and an IEC 62133-2 or UL 1642 certificate. Get both PDFs before design freeze. [DESIGN: not a coin cell; temperature-gated charging; ship mode; non-replaceable cell; room for swelling.] | $0 if the vendor supplies documents; retest $5k-8k and 4-6 weeks (estimate) |
| 4 | Transport | Ship with the cell installed as UN3481 under 49 CFR 173.185(c) and IATA PI 967 Section II, at about 30% state of charge. Keep the test summary available. Plan for the lithium battery mark on packages whenever a consignment has more than two packages. | $0 beyond packaging |
| 5 | Battery charger energy rules | Presume the DOE battery-charger standard applies; test the charger system and file the federal certification, then list in the California MAEDbS database. [DESIGN: charger IC with termination and microamp-level quiescent current.] | $1k-3k (estimate, combined with item 6) |
| 6 | California | Prop 65 warning in the chemical-naming short form (or supplier declarations supporting no warning). SB 1215 battery-embedded product notice to retailers, copied to CalRecycle, each year. | see item 5 |
| 7 | LEDs | Keep the LED maker's IEC 62471 statement on file. [DESIGN: visible or near-IR LEDs only; no UV; no laser or VCSEL emitters.] | $0 |
| 8 | IP67 | IEC 60529 IP6X and IPX7 report from a US lab. [DESIGN: non-porous print process; one gasketed or bonded seal plane; bonded windows; sealed charge contacts; no button shaft; allowance for pressure swing; leak test on every unit.] | $1k-3k and 1-2 weeks (estimate) |
| 9 | Origin claim | "Designed and assembled in USA with US and imported parts". Keep a BOM origin table and CM / printer invoices. Never an unqualified "Made in USA". | $0 |
| 10 | Canada (only if sold there) | ICES-003 Class B from the same test data; "Contains IC: (module number)"; bilingual statements. | $300-800 (estimate) |
| 11 | Patents | Freedom-to-operate review of the electronic ball-marker patents the report lists. | not estimated |

Indicative total from the report's own line items: $15.5k-23.5k (US), $15.8k-24.3k with Canada. Arithmetic confirmed; inputs UNVERIFIED.

### 2.3 Fallbacks

- If no pouch cell fits: a rechargeable coin cell is possible but brings in 16 CFR 1263 / UL 4200A testing, warnings and a certificate.
- If the BLE module does not fit: a chip-down radio needs its own FCC certification, estimated by the first report at $10k-20k and 4-8 weeks (unsourced). Avoid.

## 3. Candidates

There are no purchasable parts in this topic. "MPN" is n/a throughout; "interface / supply" is n/a throughout; "US distributors / stock" is replaced by the US body or lab that does the work. All specs, dates and prices are the first report's values and are UNVERIFIED in this pass.

| Name | MPN | Maker / HQ | Key specs | Dimensions | Interface / supply | Price | US provider | Lifecycle | Verdict |
|------|-----|------------|-----------|------------|--------------------|-------|-------------|-----------|---------|
| Positioning A: practice / training device | n/a | USGA (USA), The R&A (UK) | Full feature set. Not permitted in a round: Rule 4.3a(1); Equipment Rules alignment-device definition; Rule 14.1a | Thresholds 25.4 mm height, 50.8 mm horizontal with line features; electronics clause at any size | n/a | $0 | none needed | 2023 Rules of Golf in force; Equipment Rules version not confirmed | Recommended |
| Positioning B: locked restricted mode (distance only) | n/a | USGA / The R&A | Slope, break, grain, aim line and all directional graphics off; lock indicator | No line on the top face in this mode | n/a | firmware only | USGA Equipment Standards ruling needed (process UNVERIFIED) | No ruling exists | Fallback |
| Positioning C: market as conforming for rounds | n/a | USGA / The R&A | Conflicts with Rules 4.3a(1), 10.2b, 14.1a | n/a | n/a | n/a | n/a | Prohibited | Rejected |
| FCC Part 15B Class B by SDoC, host with pre-certified BLE module | n/a | FCC (USA) | 47 CFR 15.101, 15.109, 15.19, 2.1077; KDB 996369, KDB 784748 | Marking area on base or packaging | n/a | $1.5k-5.5k one-time; $0 government fee | US accredited EMC lab (Element, DLS, Compliance Testing, Nemko named; no quotes) | Current; FCC 26-73 changes reported, UNVERIFIED | Recommended |
| FCC certification of a chip-down radio (15.247) | n/a | FCC (USA) | Own FCC ID through a TCB, plus 15B; ISED repeated | n/a | n/a | $10k-20k, 4-8 weeks (estimate) | US TCB / lab | Current | Rejected |
| FCC / ISED marking: base marking, e-label screen, manual text | n/a | FCC (USA), ISED (Canada) | "Contains FCC ID", "Contains IC"; statement in manual for small devices; e-label within three menu steps (secondary source) | About 12 x 6 mm text block at 1 mm characters (estimate) | n/a | $0 | n/a | Current | Recommended |
| ISED Canada: ICES-003 Class B + "Contains IC" | n/a | ISED (Canada) | Module must hold an ISED number; label wording per current ICES-003 / ICES-Gen | n/a | n/a | $300-800 (estimate) | same US EMC lab | Current; issue numbers not confirmed | Viable |
| Bluetooth SIG qualification of the end product | n/a | Bluetooth SIG (USA) | Required for any product using Bluetooth; references module's qualified design | n/a | n/a | $12,000 Adopter; $6,000 Associate (schedule of 1 Mar 2026 as reported) | SIG online qualification workspace | Reported current schedule | Recommended |
| Battery: Li-polymer pouch cell with PCM and documents | n/a (cell chosen elsewhere) | n/a | UN 38.3 test summary; IEC 62133-2 and/or UL 1642; outside 16 CFR 1263 by geometry (reading, not confirmed) | set by mechanical design | n/a | $0 extra with vendor documents | US distributor that supplies the documents | Standards current | Recommended |
| Battery: coin / button cell | n/a | n/a | Falls under 16 CFR 1263 / ANSI/UL 4200A-2023; warnings; certificate | n/a | n/a | UL 4200A test cost not sourced | US test lab | In force | Rejected |
| Transport: UN3481 contained in equipment | n/a | US DOT PHMSA (USA), IATA (Canada) | 49 CFR 173.185(c): under 20 Wh per cell, 100 Wh per battery; IATA PI 967 Section II; 30% state of charge recommended | n/a | n/a | $0 beyond packaging | UPS / FedEx / USPS programmes | IATA DGR 67th edition, 2026 | Recommended |
| LED photobiological safety file (IEC 62471) | n/a | IEC (Switzerland) | Exempt group expected for low-power pulsed LEDs facing turf; no US mandate for LEDs | n/a | n/a | $0 with LED vendor data | LED maker statement | Current | Viable |
| California package: Prop 65, SB 1215, CEC Title 20 | n/a | OEHHA, CalRecycle, California Energy Commission (USA) | Short-form warning names a chemical; battery-embedded fee and notices; charger listing in MAEDbS | n/a | n/a | $1k-3k (estimate) | CEC filing, CalRecycle notice | In force 2026 as reported | Recommended |
| Origin claim, qualified | n/a | FTC (USA) | "Designed and assembled in USA with US and imported parts"; substantiation file | n/a | n/a | $0 | n/a | 16 CFR 323 in force | Recommended |
| Origin claim, unqualified "Made in USA" | n/a | FTC (USA) | Needs "all or virtually all" US content | n/a | n/a | n/a | n/a | 16 CFR 323 | Rejected |
| IP67 verification (IEC 60529) | n/a | IEC (Switzerland) | IP6X dust-tight; IPX7 30 min at 1 m | n/a | n/a | $1k-3k (estimate) | DLS Electronic Systems named; no quote | Current | Recommended |
| Tariff exposure on foreign-made parts | n/a | USTR / CBP / Commerce (USA) | Section 301 and Section 232 layers as reported; embedded in US distributor prices | n/a | n/a | 10-15% BOM contingency suggested | distributor is importer of record | Volatile | Viable (monitor) |

## 4. Key findings with confidence

"Report confidence" is the first report's own rating. "This pass" is always "not confirmed against a live source"; the last column records whether reviewer recollection agrees. Reviewer recollection is not a source.

| # | Finding | Report confidence | Reviewer recollection | Confidence after review |
|---|---------|-------------------|-----------------------|-------------------------|
| 1 | GreenLine is an alignment device by definition because it contains electronics / optics and gauges slope, regardless of size | high | Agrees with the three criteria and the 1 Jan 2020 effective date. Current Equipment Rules version not known. | medium-high, UNVERIFIED |
| 2 | Rule 4.3a(1) allows distance / direction only; slope, recommended line and alignment-device use are each barred | high | Agrees, including the Clarification 4.3a(1)/1 examples (bottle as level, bubble level, weight on a string) | medium-high, UNVERIFIED |
| 3 | Size limits are 1.0 in height and 2.0 in horizontal (the latter with line / appendage features); GreenLine is inside both | high | Agrees; conversions confirmed by arithmetic | medium-high, UNVERIFIED |
| 4 | The marker must be lifted before the stroke (Rule 14.1a, one penalty stroke) and an object may not be set down to help aiming (Rule 10.2b(3)) | high | Agrees; on the putting green Rule 10.2b(2) is the specific provision | medium-high, UNVERIFIED |
| 5 | Rule 4.3 applies in casual rounds; rounds using the slope / aim features should not be posted | medium | Agrees on Rule 4.3. Handicap point is a simplification (see section 1) | medium, UNVERIFIED |
| 6 | Green-reading material limits (3/8 in per 5 yd, i.e. 1:480; book 7 x 4.25 in) constrain any companion app | medium | Agrees; 1:480 confirmed by arithmetic | medium, UNVERIFIED |
| 7 | FCC: Part 15B by SDoC with an unmodified pre-certified module; host stays responsible for 15B test, labelling and a US responsible party | high | Agrees (15.101 table, 2.1077, KDB 996369, KDB 784748; Class B limits 40 and 54 dBuV/m at 3 m) | medium-high, UNVERIFIED |
| 8 | FCC 26-73 (29 Oct 2026): certification testing limited to US / reciprocal-economy labs from 1 Dec 2028; proposal to require accredited labs for SDoC | medium | Beyond recollection. The docket number matches the known 2025 test-lab proceeding. | low, UNVERIFIED |
| 9 | Bluetooth SIG qualification is required and costs $12,000 (Adopter) from 1 Mar 2026 | medium | Previous fee $11,040 agrees. New schedule and the "Contributing Adopter" tier not recalled. $2,500 small-company programme status unknown. | low-medium, UNVERIFIED |
| 10 | A sub-1 Wh cell in equipment ships under small-cell exceptions; UN 38.3 summary needed in practice; UL / IEC cell standards are marketplace expectations | medium | Agrees; mark exception is limited to consignments of two packages or fewer | medium, UNVERIFIED |
| 11 | Reese's Law is triggered by cell geometry (diameter greater than height); a rectangular pouch cell is out of scope | medium | Agrees on the definition; the pouch-cell conclusion is a reasonable reading but not a CPSC statement | medium, UNVERIFIED |
| 12 | California: Prop 65 short form must name a chemical; SB 1215 notices and fee; CEC charger listing | medium | Agrees on Prop 65 dates and the 1 Jan 2026 fee start. Reviewer recalls the fee as 1.5% of retail price capped at $15. | medium, UNVERIFIED |
| 13 | Unqualified "Made in USA" is unavailable; a qualified claim is the ceiling; enforcement stepped up in 2026 | medium | Agrees on 16 CFR 323 and the "all or virtually all" standard. 2026 enforcement events not recalled or beyond recollection. | medium (rule), low (2026 events), UNVERIFIED |
| 14 | Tariffs: IEEPA tariffs struck down 20 Feb 2026; Section 122 surcharge to 24 Jul 2026; Section 301 forced-labor layer 10 / 12.5% since; 50% on Chinese semiconductors | medium | Agrees up to mid-2026 (court ruling, Section 122, 50% semiconductor rate, 23 Jun 2027 step, Section 232 action of 14 Jan 2026, exclusions to 10 Nov 2026). The 24 Jul 2026 replacement tariffs are beyond recollection. | medium (to mid-2026), low (after), UNVERIFIED |
| 15 | IPX7 is 30 min at 1 m; IP67 adds dust-tight | medium | Agrees. Depth rule wording corrected in section 5. | medium-high, UNVERIFIED |
| 16 | LED ring is a documentation item; lasers / VCSELs would bring FDA laser-product rules | low | Agrees | medium, UNVERIFIED |
| 17 | Canada: "Contains IC" on the host and an ICES-003 Class B statement; no separate radio certification | medium | Agrees in substance; label wording likely differs (section 5) | medium, UNVERIFIED |
| 18 | US patents exist on electronic ball-marker alignment devices | low | Not recalled | low, UNVERIFIED |

## 5. Verification table

Verdict key: confirmed = checked in this pass (arithmetic or internal consistency only); corrected = an error found by arithmetic or internal consistency; unverifiable = needs a live source that could not be reached. No item is marked contradicted.

| # | Item | Verdict | Corrected value | Note |
|---|------|---------|-----------------|------|
| 1 | Candidate "Positioning A: practice / training device" (recommended) | unverifiable | | No MPN. Rests on Rule 4.3a(1) and the alignment-device definition, both UNVERIFIED in this pass and both consistent with reviewer recollection. Reasoning is sound. |
| 2 | Candidate "Positioning B: locked restricted mode" (fallback) | unverifiable | | Correctly described as unresolved. Do not market as tournament-legal. USGA submission process not known. |
| 3 | Candidate "FCC Part 15B by SDoC with pre-certified module" (recommended) | unverifiable | | Legal path consistent with reviewer recollection of 15.101, 2.1077, 2.909, KDB 996369. Cost range comes partly from a low-reliability site (markready.pages.dev); obtain lab quotes. |
| 4 | Candidate "FCC / ISED marking implementation" (recommended) | unverifiable | | E-label rule (47 CFR 2.935, KDB 784748) consistent with reviewer recollection. Marking area size is an estimate. |
| 5 | Candidate "Bluetooth SIG qualification", $12,000 Adopter fee effective 1 Mar 2026 (recommended) | unverifiable | | bluetooth.com unreachable. Prior $11,040 agrees with reviewer recollection ($9,600 x 1.15, arithmetic confirmed). New schedule not recalled. |
| 6 | Candidate "Li-polymer pouch cell with UN 38.3 summary and IEC 62133-2 / UL 1642" (recommended) | unverifiable | | No cell MPN in this report. Document requirements consistent with reviewer recollection. Pouch-cell exclusion from 16 CFR 1263 is a reading, not a CPSC statement. |
| 7 | Candidate "Transport as UN3481 in equipment, 49 CFR 173.185(c) / PI 967" (recommended) | unverifiable | Reviewer recollection, UNVERIFIED: mark exception applies only where the consignment has no more than two packages | The report's excerpt was truncated at this condition. Plan for the mark on multi-package shipments. |
| 8 | Candidate "California package" (recommended) | unverifiable | | Dates consistent with reviewer recollection. Cost is an estimate. Add the DOE federal charger item (row 27). |
| 9 | Candidate "Qualified origin claim" (recommended) | unverifiable | | Consistent with reviewer recollection of FTC guidance. Have counsel confirm final wording. |
| 10 | Candidate "IP67 verification at a US lab" (recommended) | unverifiable | | Test conditions consistent with reviewer recollection of IEC 60529. Price and lead time are estimates; obtain quotes. |
| 11 | Alignment-device thresholds: height greater than 1.0 in; horizontal exceeds 2.0 in with features; electronics / slope clause; effective 1 Jan 2020 | unverifiable | | usga.org unreachable. Consistent with reviewer recollection. Current Equipment Rules version not read by either pass. |
| 12 | Conversions: 1.0 in = 25.4 mm; 2.0 in = 50.8 mm; 44 mm = 1.73 in; 7 mm = 0.28 in | confirmed | | Arithmetic. 40 mm = 1.57 in. |
| 13 | Rule 4.3a(1) allowed / not-allowed lists; penalty general penalty then disqualification | unverifiable | | randa.org unreachable. Consistent with reviewer recollection; the second-breach penalty applies to a breach unrelated to the first. |
| 14 | Rule 14.1a: remove ball-marker before the stroke, one penalty stroke; Rule 10.2b(3) heading and "set an object down" meaning | unverifiable | Reviewer recollection, UNVERIFIED: also cite Rule 10.2b(2) for a ball on the putting green | Consistent with reviewer recollection. |
| 15 | Green-reading scale 3/8 in per 5 yd equals 1:480 | confirmed | | Arithmetic: 180 in / 0.375 in = 480. The limits themselves are UNVERIFIED. |
| 16 | Citation "Equipment Rules Part 6, section 7" | corrected | Section number unresolved; cite by title "Definition of Alignment Device and Treatment of Ball-Markers (Rule 4.3)" | Internal inconsistency: the URL the report gives for this section ends in part-6-rule-8. |
| 17 | FCC Class B radiated limits 40 dBuV/m (30-88 MHz) and 54 dBuV/m (above 960 MHz) at 3 m; responsible party must be in the US | unverifiable | | Consistent with reviewer recollection of 15.109(a) (100 and 500 uV/m; dB conversion confirmed by arithmetic) and 2.1077 / 2.909. |
| 18 | FCC 26-73 adopted 29 Oct 2026; lab restriction for applications from 1 Dec 2028; SDoC accredited-lab proposal | unverifiable | | docs.fcc.gov unreachable; beyond reviewer recollection. The recommended action (use a US accredited lab) does not depend on it. |
| 19 | Bluetooth SIG Associate $6,000, Contributing Adopter $8,000 first qualification; $2,500 small-company programme | unverifiable | | Not recalled. Treat the $2,500 programme as unavailable for budgeting. |
| 20 | 49 CFR 173.185(c) thresholds 20 Wh per cell, 100 Wh per battery; IATA 2026: 30% state of charge recommended for PI 967, mandatory for PI 966 above 2.7 Wh | unverifiable | | Consistent with reviewer recollection. A 1 Wh cell is about 270 mAh at 3.7 V; 2.7 Wh is about 730 mAh (arithmetic). |
| 21 | Reese's Law: covered battery is a single cell with diameter greater than height; zinc-air excluded; ANSI/UL 4200A-2023; packaging label date 21 Sep 2024 | unverifiable | | Consistent with reviewer recollection. |
| 22 | Prop 65 short-form change effective 1 Jan 2025, old form usable to 31 Dec 2027; SB 1215 fee from 1 Jan 2026, notice by 1 July each year, report from 1 July 2027 | unverifiable | | Prop 65 dates and fee start consistent with reviewer recollection. Annual-report date not recalled. |
| 23 | CEC: USB charger systems in scope since 1 Feb 2014 | unverifiable | Reviewer recollection, UNVERIFIED: the 2014 date applied to large USB charger systems (20 Wh or more with a screen); other small consumer chargers were in scope from 1 Feb 2013 | Not decision-critical; current treatment depends on federal preemption (row 27). |
| 24 | FTC 16 CFR 323 effective Aug 2021, "all or virtually all"; March 2026 executive order; July 2026 warning letters to seven companies | unverifiable | | Rule consistent with reviewer recollection. 2026 events not recalled or beyond recollection. |
| 25 | Tariffs: Supreme Court ruling 20 Feb 2026; Section 122 from 24 Feb to 24 Jul 2026; Section 301 forced-labor tariffs 10 / 12.5% from 24 Jul 2026; 50% on Chinese semiconductors; 23 Jun 2027 step; Section 232 of 14 Jan 2026; 178 exclusions to 10 Nov 2026 | unverifiable | | 24 Feb 2026 plus 150 days is 24 Jul 2026 (arithmetic confirmed, consistent with the statutory 150-day limit). Items to mid-2026 consistent with reviewer recollection; the 24 Jul 2026 tariffs are beyond it. |
| 26 | IPX7 depth rule "lowest point 1,000 mm or highest point 150 mm below the surface, whichever is deeper"; IP6X talc, up to 8 h, 2 kPa | unverifiable | Reviewer recollection, UNVERIFIED: enclosures under 850 mm tall are placed with the lowest point 1,000 mm below the surface; the 150 mm rule is for enclosures 850 mm or taller. Duration 30 min. | For a 7 mm puck the result is the same: 1 m. IEC 60529 also limits the water-to-sample temperature difference to 5 K, so the report's 50 C pre-soak is harsher than the standard. |
| 27 | DOE battery-charger scope "not confirmed" | unverifiable | Reviewer recollection, UNVERIFIED: 10 CFR 430.32(z) covers battery chargers for consumer products including built-in, USB-powered ones; a single 3.7 V cell under 100 Wh is product class 2 with a limit of 0.1440 x battery energy + 2.95 kWh per year; certification is filed with DOE | Treat as applicable until confirmed. A charger IC with low quiescent current should pass easily. |
| 28 | Cost total "roughly $16k-25k" | confirmed | $15.5k-23.5k US items; $15.8k-24.3k with Canada | Arithmetic on the report's own line items. Inputs UNVERIFIED. Excludes patent review, UN 38.3 retest, DOE testing, USGA submission. |
| 29 | Canada label example "CAN ICES-3 (B)/NMB-3 (B)"; RSP-100 Issue 12 | unverifiable | Reviewer recollection, UNVERIFIED: current ICES-003 wording is "CAN ICES-003(B) / NMB-003(B)" | Confirm against the current ISED documents before artwork. |
| 30 | Patents US 10,905,930; US 11,278,779; US 9,433,839; US 9,108,087 | unverifiable | | Titles only in the report; numbers, owners, claims and status not checked by either pass. |
| 31 | Handicap: rounds using the device are not acceptable scores | unverifiable | Reviewer recollection, UNVERIFIED: unacceptable when the breach is not penalised or a Rule is deliberately ignored | User guidance unchanged: do not post such rounds. |

## 6. Risks

1. Verification gap. Neither the first report nor this review read the Rules of Golf, the Equipment Rules or the Bluetooth fee schedule from the primary pages. The Rules wording comes from search excerpts. Manual and packaging text must not be finalised from this document.
2. Rules risk is structural. The alignment-device definition is triggered by the presence of electronic or optical components in a ball-marker. The product cannot be advertised for rounds played under the Rules of Golf. This limits the market to practice and training use.
3. A restricted or "tournament" mode could lead users into penalties if it is marketed without a written decision. The cameras must face the hole, which orients the marker along the line of play.
4. Three dated claims fall after the reviewer's knowledge horizon and have no corroboration at all: FCC 26-73 (29 Oct 2026), the Section 301 forced-labor tariffs (24 Jul 2026) and the July 2026 FTC warning letters. The file names and docket numbers cited look plausible, but that is not evidence.
5. The Bluetooth SIG fee is the largest single cost and is unconfirmed. The small-company discount may no longer exist.
6. FCC cost figures rest partly on a low-reliability source. Lab quotes are needed.
7. Module-integration conditions: any antenna change, metal near the antenna, or use outside the grant's host conditions voids the modular approval. Wet turf under the puck will detune the antenna. The module's RF-exposure condition for a hand-held device has to be checked in its grant.
8. Federal battery-charger energy rules may apply and were not in the first report's checklist.
9. Battery documentation: small Li-polymer cells sold through hobby channels often lack a traceable UN 38.3 test summary or safety certificate. This blocks marketplace listing and air shipment.
10. Shipping: the lithium battery mark exception is narrow. Multi-package consignments need the mark.
11. Thermal: a sealed dark puck in direct sun can exceed lithium-ion charge and storage temperature limits. Charging must be temperature-gated and the cell needs swelling room.
12. IP67 on a 3D-printed enclosure: porous prints, bonded windows and charge contacts are common leak paths. Sun heating followed by cold-water immersion creates a pressure difference across the seals.
13. Origin claims: any "Made in USA" shorthand in listings or packaging creates penalty exposure under 16 CFR 323.
14. Tariff volatility can move BOM cost for image sensors, displays and cells between prototype and production.
15. Patents on electronic ball-marker alignment devices were found by title only. Claims and status are unknown.
16. California obligations (Prop 65 format, SB 1215 notices, charger listing) are enforced through retailers and private plaintiffs and are easy to miss.

## 7. Open questions

1. Does the current Equipment Rules text keep the clause "includes optical or electronic components", what is its section number, and what does it say about using such an object only to mark the spot of a ball?
2. Will USGA Equipment Standards issue a written decision on a locked distance-only mode? What are the submission steps, fee and turnaround?
3. Exact current wording of Rule 4.3a(1), Clarification 4.3a(1)/1, Rule 10.2b(2) and (3), Rule 14.1a and Model Local Rule G-5, for quotation in the manual.
4. USGA position on posting a score after a slope-measuring device was used in a casual round.
5. Is the Bluetooth SIG fee $12,000 for an Adopter member today, and does any reduced-fee programme exist for small companies?
6. Does FCC 26-73 exist as described, and where was the chosen BLE module's grant testing performed?
7. What host conditions does the chosen module's grant impose (antenna, co-location, portable-use RF exposure)?
8. Does the CPSC confirm that a rectangular Li-polymer pouch cell is outside 16 CFR 1263?
9. Does the DOE battery-charger standard cover this product, which product class applies, and what must be filed before first sale? What does the California Energy Commission then require?
10. Current text of 49 CFR 173.185(c)(3) and the chosen carrier's extra requirements.
11. Quotes and lead times from US labs for FCC 15B SDoC, IEC 60529 IP67 and, if needed, UN 38.3 / IEC 62133-2.
12. Do state battery stewardship laws outside California reach products with embedded, non-removable cells? (Raised by this review; not researched.)
13. Current tariff treatment and country of origin for each camera module, display and cell; outcome of the Section 301 exclusions due to lapse on 10 Nov 2026.
14. Scope, owner and status of the four patents listed.
15. Current ISED wording for the ICES-003 label and the current RSP-100 issue.

## 8. Sources

### 8.1 Pages this review tried to open (all failed; nothing was read)

1. https://www.usga.org/equipment-standards/equipment-rules-2019/equipment-rules/part-6-rule-8.html (host not resolvable from this session)
2. https://www.randa.org/en/rog/the-rules-of-golf/rule-4 (host not resolvable from this session)
3. https://www.bluetooth.com/fee-schedule/ (host not resolvable from this session)
4. https://docs.fcc.gov/public/attachments/FCC-26-73A1.pdf (host not resolvable from this session)

### 8.2 Sources cited by the first report (NOT opened by this review; listed so a follow-up pass can check them)

Rules of Golf and handicapping

5. https://www.usga.org/content/dam/usga/pdf/Equipment/Notice%20to%20Ball-Marker%20Manufacturers%20(Final)%20(1).pdf
6. https://www.usga.org/content/usga/home-page/rules-hub/rulesarticles/clarifications-of-the-2019-rules-of-golf-nonav.html
7. https://www.usga.org/content/dam/usga/pdf/2022/rules/Clarifications%20of%20the%202019%20Rules%20of%20Golf%20-%20April%202022.pdf
8. https://www.randa.org/sw/rog/the-rules-of-golf/rule-4
9. https://rulesworkshops.usga.org/content/dam/usga/pdf/2025/2023%20Update%20USGA-DMD.pdf
10. https://www.usga.org/content/usga/home-page/custom-search-pages/rules/2019-golf-rules-and-interpretations/rule-4-interpretations.html
11. https://www.randa.org/sw/rog/clarifications/rule-4
12. https://archive.oga.org/node/2955
13. https://www.usga.org/content/dam/usga/pdf/Equipment/DMDs-2016-2018a.pdf
14. https://fsga.org/News/Details/1913
15. https://www.randa.org/rog/the-rules-of-golf/rule-14
16. https://usga.org/content/usga/home-page/rules/rules-2019/players-edition/rule-14.html
17. https://www.nationalclubgolfer.com/rules/rules-of-golf-explained-ball-marker-putt/
18. https://www.randa.org/rog/the-rules-of-golf/rule-10
19. https://www.randa.org/en/players-rule-finder/players-rule-finder/other-rules/advice-and-other-help/setting-down-object-to-help-with-aiming-taking-stance-or-swinging
20. https://www.usga.org/rules-hub/distance-measuring-devices/dmd-faqs.html
21. https://www.usga.org/handicapping/roh/Content/rules/2%201b%20Played%20by%20the%20Rules%20of%20Golf.htm
22. https://www.usga.org/handicapping/roh/Content/rules/2%201-Acceptability%20of%20Scores.htm
23. https://golf.com/instruction/rules/legal-post-scores-rangefinder-slope-function-rules
24. https://www.usga.org/content/dam/usga/pdf/2023/rules/Green%20Reading%20Materials_FAQs_2023%20-%20Final.pdf
25. https://www.usga.org/content/dam/usga/pdf/2019/rules/INTP4.3a_1.pdf
26. https://www.usga.org/content/usga/home-page/rules-hub/2023-rules-of-golf/model-local-rule-g-11.html
27. https://www.usga.org/content/dam/usga/pdf/2021/rules/MLR-G11-and-Additional-Guidance-FINAL.pdf
28. https://usga.org/content/dam/usga/pdf/2023/rules/ModelLocalRuleG12.pdf

FCC and ISED

29. https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-B/section-15.101
30. https://www.law.cornell.edu/cfr/text/47/2.1077
31. https://fcc.gov/sites/default/files/33-Modules-Integration-Instructions-TCB_Oct_2023.pdf
32. https://fcc.gov/sites/default/files/32-KDB-996369-Modules-TCB_Oct_2023.pdf
33. https://www.ezurio.com/resources/white-papers/fcc-guidance-on-transmitter-modules
34. https://www.nemko.com/hubfs/Radio%20-%20Testing%20Strategies%20and%20best%20practice%20for%20using%20approved%20modules%20per%20FCC%20KDB99369.pdf
35. https://markready.pages.dev/guides/fcc-certification-cost
36. https://markready.pages.dev/learn/fcc-label-requirements
37. https://compliancetesting.com/fcc-sdoc/
38. https://transition.fcc.gov/oet/ea/presentations/files/nov19/12-SDoC-JS.pdf
39. https://docs.fcc.gov/public/attachments/DOC-426300A1.pdf
40. https://docs.fcc.gov/public/attachments/DOC-425721A1.pdf
41. https://www.dlapiper.com/en/insights/publications/2026/10/fcc-to-vote-on-limiting-equipment-authorization-testing
42. https://www.element.com/about-element/news/2026/11/04/fcc-equipment-authorization-rule-changes
43. https://www.gmalabs.com/post/fcc-test-lab-reciprocity-rules-adopted-2028-cutoff-set
44. https://onlinedocs.microchip.com/oxy/GUID-26060FFF-4EA0-483D-BCBB-39AF46A5A76C-en-US-6/GUID-D5EDC679-1AE5-4587-9F95-B830E7B96AED.html
45. https://fcc.report/FCC-ID/2AGN8-ZM001/4480247.pdf
46. https://publications.gc.ca/collections/collection_2023/isde-ised/Iu64-175-2016-eng.pdf

Bluetooth SIG

47. https://www.bluetooth.com/develop-with-bluetooth/join/
48. https://devzone.nordicsemi.com/f/nordic-q-a/126424/bluetooth-sig-fees
49. https://www.tuvsud.com/en-us/services/testing/bluetooth-qualification
50. https://community.infineon.com/t5/Knowledge-Base-Articles/Queries-on-BLE-Qualification-and-Declaration-Processes/ta-p/259951
51. https://www.spilma.com/en/guides/bluetooth-sig-qualification

Lithium battery and Reese's Law

52. https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-173/subpart-E/section-173.185
53. https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/2023-07/Lithium%20Battery%20Guide.pdf
54. https://www.iata.org/contentassets/05e6d8742b0047259bf3a700bc9d42b9/lithium-battery-guidance-document.pdf
55. https://www.hazmatschool.com/blog/2026-iata-lithium-battery-shipping-regulations/
56. https://www.compliancegate.com/amazon-lithium-batteries-requirements/
57. https://amzbase.com/guides/amazon-fba-lithium-battery-requirements/
58. https://www.cpsc.gov/Business--Manufacturing/Business-Education/Business-Guidance/Button-Cell-and-Coin-Battery
59. https://www.cpsc.gov/FAQ/Button-Cell-and-Coin-Battery-FAQs
60. https://www.federalregister.gov/documents/2023/09/21/2023-20333/safety-standard-for-button-cell-or-coin-batteries-and-consumer-products-containing-such-batteries
61. https://www.law.cornell.edu/cfr/text/16/1263.1
62. https://www.lexology.com/library/detail.aspx?g=fa1539f0-211c-4005-b30a-f0502b1aeba2
63. https://www.intertek.com/batteries/reeses-law/

California

64. https://www.squirepattonboggs.com/insights/publications/california-prop-65s-shortform-warnings-will-no-longer-be-short/
65. https://ul.com/news/amendment-california-prop-65
66. https://calrecycle.ca.gov/electronics/embeddedbatteries/
67. https://content.govdelivery.com/accounts/CALRECYCLE/bulletins/41de528
68. https://www.energy.ca.gov/sites/default/files/2020-05/2018-06-07_Battery_Chargers_Advisory_ada.pdf
69. https://www.energy.ca.gov/programs-and-topics/programs/appliance-efficiency-program-outreach-and-education/federal-battery

FTC origin claims

70. https://www.ftc.gov/business-guidance/resources/complying-made-usa-standard
71. https://www.ftc.gov/made-in-usa-rule
72. https://www.ftc.gov/legal-library/browse/enforcement-policy-statement-us-origin-claims
73. https://www.hklaw.com/en/insights/publications/2026/03/executive-order-signals-heightened-enforcement-of-made-in-us
74. https://www.mintz.com/insights-center/viewpoints/2171/2025-12-16-made-usa-claims-compliance-risks-ftc-enforcement-and

Tariffs

75. https://www.bakerdonelson.com/forced-labor-section-301-tariffs-imposed-to-replace-expiring-section-122-tariffs-what-importers-need-to-know
76. https://www.rvia.org/news-insights/section-122-tariffs-replaced-new-section-301-forced-labor-tariffs
77. https://octopart.com/pulse/p/tariff-reset-pcb-workarounds
78. https://www.cofactr.com/articles/definitive-guide-to-semiconductor-tariffs
79. https://www.sec.gov/Archives/edgar/data/1387467/000162828026059261/aosl-20260630.htm
80. https://www.sec.gov/Archives/edgar/data/855658/000114036126010153/ny20060701x3_ars.pdf
81. https://www.sec.gov/Archives/edgar/data/0000916789/000091678926000138/hele-20260831.htm

Ingress protection and LED safety

82. https://www.dlsemc.com/ipx7-and-ipx8-immersion-testing/
83. https://www.dlsemc.com/iec-60529-and-en-60529-testing/
84. https://code.dcldesign.co.uk/index.php/IP_Rating
85. https://look.ams-osram.com/m/1d720a7b18ab3fce/original/Details-on-photobiological-safety-of-LED-light-sources.pdf
86. https://laser-led-lamp-safety.seibersdorf-laboratories.at/fileadmin/uploads/intranet/dateien/le/laser/ilsc_2019_schulmeister_ohagan_sliney_lamp_and_led_safety_-_classificatio....pdf
87. https://www.lasermet.com/laser-safety-service/led-testing-to-en-62471/

Patents

88. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10905930
89. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11278779
90. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9433839
91. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9108087
