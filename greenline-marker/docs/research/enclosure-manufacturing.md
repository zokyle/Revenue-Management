# GreenLine research: 3D-printed enclosure process, sealing, optical windows, US PCB fab and assembly vendors

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web. The first report had the same limitation, so **no vendor fact in this topic has been checked against a live page by either pass.**

- Web search: four queries were attempted (OSH Park 4-layer specs, HP PA12 datasheet, Protolabs MJF design rules, Carbon EPX 82 datasheet). All four were refused with "web search budget is used up" (a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `docs.oshpark.com`, `www.protolabs.com`, `www.carbon3d.com` and `www.edmundoptics.com` all failed to resolve (hosts outside this session's allowed network domains). No further hosts were tried, as the tool instructs. The local proxy status confirms policy denials for non-allowed hosts.
- No workaround (shell download, third-party reader, archive) was attempted, because those are blocked or disallowed.

Consequences:

- **Every part number, datasheet value, price, stock level, lead time, vendor capability and vendor ownership statement in this document is UNVERIFIED.** They are carried forward from the first report, which itself wrote them from model memory with no sources.
- What was verified here: every derivation and unit conversion in the first report (recomputed with a local script), the internal consistency of its geometry and stack-up numbers, and the engineering logic. This produced several corrections, listed in section 6.
- Where the reviewer's own recollection of a datasheet or vendor page (model training data, to about mid-2026) agrees or disagrees with the first report, that is recorded as "reviewer recollection". Two models recalling the same number is not independent confirmation, and recollection does not change an UNVERIFIED mark.
- Several recommended items have **no part number at all** (thread-forming screws, sapphire camera windows, the ePTFE vent, the display crystal). The enclosure bill of materials therefore cannot be called ready to manufacture yet. Section 8 lists exactly what has to be looked up.

Hosts that need to be allowed in the session's network settings (or the search budget raised) before this topic can be closed: `docs.oshpark.com`, `www.protolabs.com`, `www.carbon3d.com`, `www.edmundoptics.com` (the four that were tried), and also `www.xometry.com`, `www.hp.com`, `formlabs.com`, `www.mcmaster.com`, `www.thorlabs.com`, `www.swissjewel.com`, `www.esslinger.com`, `www.ottofrei.com`, `www.gore.com`, `www.parker.com`, `www.3m.com`, `www.pemnet.com`, `www.digikey.com`, `www.mouser.com`, `www.4pcb.com`, `bayareacircuits.com`, `www.protoexpress.com`, `www.macrofab.com`, `www.screamingcircuits.com`, `circuithub.com`, `www.tag-connect.com`, `www.labsphere.com`.

## 1. Summary

The first report's engineering conclusions survive the checks that could be made. Its arithmetic is correct almost everywhere, and its recalled datasheet values agree with the reviewer's recollection in nearly every case. Nothing found here overturns the recommendation. It does need the amendments below.

Conclusions that stand:

1. Production enclosure in HP Multi Jet Fusion PA12, dyed black and vapor smoothed, from US bureaus; Carbon DLS epoxy as the tight-tolerance fallback; desktop SLA for prototypes; low-HDT photopolymers excluded from shipped units.
2. A bonded seal (foam acrylic tape ring for the display cover and base plate, light-cure adhesive for the camera windows) instead of an O-ring. The stronger argument is space, not tolerance: any standard O-ring gland costs 3-4 mm of radius or about 4 mm of rim height in a 40-44 x 7 mm puck.
3. A pressure-equalisation vent. The 17.3 kPa and 13.9 N figures are correct, and the case is stronger than the first report made it (altitude and air freight add as much again).
4. Sapphire for the turf-level camera windows; glass for the display cover.
5. The printed shell must not be the optical or tilt reference (0.3 mrad over 33 mm is 9.9 um).
6. The 0.8 mm 4-layer board cannot come from OSH Park's 4-layer service if that service is 1.6 mm only (UNVERIFIED; reviewer recollection agrees).
7. Calibration after final closure, with a flip test.

Corrections and additions from this review:

- **The vent does not remove the thermal-shock vacuum.** A wet or submerged ePTFE membrane passes no air. A vented puck that equalised at 60 C and is then dunked sees the full 23.5 kPa inward differential (26.0 kPa from 70 C) across every seal and across the membrane. A perfectly sealed, unvented puck would see only 1.7 kPa of thermal vacuum in the same event. The vent is still the right choice, because it removes the sustained outward load on the adhesive, but the seals and the vent's water-entry pressure must be specified for at least 25 kPa with margin.
- **Screw holes are a leak path the first report did not address.** With a 40 mm base plate and a 40/36 mm tape ring there is no room for screws outside the seal. The die-cut ring must loop inside each screw boss so that every screw hole lies outside the sealed boundary, or each screw needs its own seal.
- **Sapphire is birefringent.** The first report lists sapphire among non-birefringent cover materials. Sapphire is a uniaxial crystal (index difference about 0.008; a 1 mm plate not cut on the c-plane gives about 8 um, roughly 15 waves, of retardance). This does not matter for the camera windows (unpolarised imaging), but a sapphire display cover would have to be c-plane. Glass remains the right display cover.
- **Polarised sunglasses are a display problem regardless of the cover.** A memory LCD has its own linear polariser. The marker lies at an arbitrary rotation relative to the golfer, so the display dims as cos-squared of the angle and blacks out near 90 degrees. This needs a quarter-wave film on the display, a fixed reading orientation, or a polariser-free display. It belongs to the display workstream but changes the cover specification.
- **Radial O-ring fallback is taller than stated.** A radial gland for a 1.78 mm cross-section needs a 2.36-2.49 mm groove plus two lands, about 4.0 mm of rim height, not 2.6 mm.
- **Vapor smoothing and 0.6-0.8 mm walls may conflict.** By reviewer recollection some bureaus ask for walls of about 1 mm or more for chemical vapor smoothing because thin sections can distort. UNVERIFIED, but it must be answered by the bureau and by printed coupons before the wall thickness is frozen. If 1.0 mm is required the puck grows by about 0.4 mm.
- **Unsupported thin faces deflect a lot.** A 0.8 mm PA12 base plate over a 36 mm span deflects 0.3 mm (clamped edge) to 1.3 mm (simply supported) under 17 kPa at room temperature, and about twice that at 70 C. A 1.0 mm glass cover over a 32 mm span sees roughly 50-160 MPa if a golfer's weight (400-800 N) lands on it unsupported. Both faces need internal support, and the production cover must be chemically strengthened.
- **Temperature calibration needs five or more points or a ramp,** not three (a quadratic through three points has zero residual and validates nothing). This matches the correction already recorded in `inertial-sensors.md`.
- **Three hard foot inserts** are needed in the base for the tilt datum. Printed PA12 pads cannot hold the micron-level reseating repeatability the tilt budget needs. This also matches `inertial-sensors.md`.
- **SLS second source: light leakage.** Standard SLS PA12 is white powder dyed after printing. At 0.6-0.8 mm it is translucent under direct sun. MJF PA12 is carbon-loaded through the wall and should be far better. Either case needs a coupon test, but the SLS fallback should specify a black or grey base powder or an internal opaque coat.
- **Minor numeric corrections:** camera angular scale is 1.64 mrad per pixel on average and 1.80 mrad per pixel at the image centre for a rectilinear 640-pixel, 60-degree lens, so 0.3 mrad is 0.17-0.18 pixel; the camera window can be up to 5.0 mm in diameter because it sits in the full-height rim, not in the 4.9-5.4 mm internal cavity.

## 2. Final recommendation

Nothing here is web-verified. Treat every vendor, part number and price as a line item to confirm.

### Enclosure

- **Production process:** HP Multi Jet Fusion, HP 3D High Reusability PA 12, dyed black, chemical vapor smoothing, ordered from two US bureaus that print in-house or guarantee US production (first report names Protolabs and Xometry with its US-only option; alternates Stratasys Direct, Endeavor 3D, DI Labs, RapidMade, Jawstec). Forecast 3D should not be relied on until its current status is confirmed (see section 5, item 48).
- **Architecture:** a top tub (rim, display-window ledge, two camera pockets on local flats of the rim) and a drop-in base plate. Nominal wall 0.8 mm, to be confirmed against the bureau's vapor-smoothing limit; every fit designed for +/-0.2 to 0.3 mm.
- **Internal support:** ribs or posts under the display stack and over the base plate so neither face spans more than about 15 mm unsupported.
- **Datum:** three hard inserts (for example stainless or ceramic pins or balls, bonded or pressed) forming the base seating points. Cameras and the precision accelerometer on one rigid board located at three points; the shell only locates that board.
- **Fallback process:** Carbon DLS EPX 82 (or RPU 130 if toughness matters more than stiffness; reviewer recollection is that RPU 130 has a much lower modulus, about 1 GPa) when a feature needs better than +/-0.1 mm.
- **Second source for nylon:** SLS PA12, with the light-leak precaution above.
- **Prototype process:** in-house SLA (Formlabs Tough 2000 class for function, a rigid resin for stiffness checks) and FDM ASA for fit.
- **Rejected for shipped units:** Carbon RPU 70, UMA 90, Formlabs Tough resins, Loctite 3D 3843, PolyJet Vero (reported HDT 45-63 C against a 60-70 C sun-soak case; the reviewer's energy balance gives about 55-77 C in a light breeze and 85-92 C in still air on an insulating surface).

### Sealing

- **Display cover:** die-cut ring of 3M VHB 5907 (0.20 mm) or 5909 (0.30 mm) on a 1.5-2.0 mm ledge, primer on the PA12 land.
- **Camera windows:** light-cure acrylic (Loctite AA 3921 / AA 3926 class, or a Dymax equivalent) cured through the window.
- **Base plate:** VHB 5909 ring plus 3-4 M1.4 thread-forming screws into PA12 bosses. The tape pattern must pass inside each screw boss (screw holes outside the sealed zone). Print screw pilots as through-holes or drill them after printing; a blind 1.1 mm x 3 mm hole is unlikely to clear of powder reliably.
- **Vent:** one adhesive ePTFE vent (first report: Gore adhesive series, part number not confirmed) in a protected position. Specify water-entry pressure of at least 50 kPa (twice the 23.5-26 kPa quench-plus-immersion differential) and confirm the adhesive rating at 70 C.
- **Seal qualification load:** 25 kPa inward (hot unit into cold water at 1 m) and 40 kPa outward for an unvented or blocked-vent case (sealed at sea level, used at 2,000 m and 70 C).
- **Battery:** 0.3 mm foam-filled swelling gap; the cell must never bear on the display.
- **Secondary protection:** conformal coat on the board, kept away from the accelerometer; no potting or underfill near it.
- **Not used:** ultrasonic welding; an O-ring (only in the DLS fallback, AS568-029, and only if about 4 mm of rim height is available).

### Windows

- **Cameras:** sapphire, AR-coated on the inner face, recessed 0.3-0.5 mm. Size the window from the chosen camera: clear aperture = 2 x (entrance-aperture radius + window distance x tan(half field of view)). A 4.0 mm window (3.0 mm clear) is enough only for a small entrance aperture close behind the window; plan on 5.0 x 0.5 mm until the camera is fixed. No stock number is known; this is an open item.
- **Display, prototype:** flat mineral-glass watch crystal, 1.0 mm thick, diameter set by the chosen display (the first report's 35.0 mm is a placeholder), from a US watch-material house. Prototype use only.
- **Display, production:** custom chemically strengthened aluminosilicate disc, 0.7-1.1 mm, black printed border, anti-fingerprint coating, from a US glass fabricator; optically bonded or AR-coated on the inside. Add the polarised-sunglasses requirement (quarter-wave film or equivalent) to the display specification.
- **Coatings:** do not design in 3M Novec-type coatings; use the fabricator's factory coating or a US-made alternative.

### PCB

- **Rule set:** 4 layers, 5/5 mil trace and space, 10 mil drill with 20 mil pad, through vias only, 15 mil copper to edge, ENIG, 0.80 mm finished thickness, 1.0 mm test pads on the bottom, no vias or traces under the accelerometer.
- **Fabrication and assembly:** a US fab that offers 0.8 mm 4-layer and in-house assembly (first report: AdvancedPCB), with a US bare-board fallback (Bay Area Circuits) and a US quick-turn assembler (Screaming Circuits) for the first builds.
- **OSH Park:** electrical bring-up spins only, if its 4-layer service is 1.6 mm (UNVERIFIED). The 1.6 mm and 0.8 mm stack-ups differ, so the same Gerbers are electrically equivalent only if nothing on the board is impedance-controlled, and radio performance must be checked on the real 0.8 mm board inside the enclosure.
- **Marketplace assemblers (MacroFab, CircuitHub):** only with written confirmation of a US bare-board source and a US build site.

### Test and calibration

- In-panel pogo test and programming (Tag-Connect TC2030-NL footprint or plain test pads), then depanel, assemble, close, leak test.
- Tilt calibration after final closure and adhesive cure: kinematic nest on a granite plate, 0/90/180/270 degree rotations, five or more temperatures or a slow ramp in both directions, validation on points not used in the fit.
- Camera-to-gravity alignment with surveyed sub-pixel targets (0.3 mrad is 0.17-0.18 pixel).
- Grain-sensor LED balance on a diffuse white standard with the base window, if any, installed.
- Leak test with the vent occluded in the fixture; for the first 100 units a dunk test including a hot-unit-into-cold-water case.

## 3. Candidate table

All specification, price, distributor and lifecycle entries are the first report's values, which that report wrote from memory with no sources. None was confirmed against a live page in this pass: **treat every cell as UNVERIFIED.** Prices are the first report's own estimates, not quotes. Stock was not checked by either pass. "Reviewer recollection" records whether the reviewer's memory agrees; it is not a source.

| Name | MPN | Maker / HQ | Key specs (as reported) | Dimensions mm (as reported) | Interface / supply | Price USD (first report's estimate) | US distributors / stock | Lifecycle (as reported) | Reviewer recollection | Verdict after this pass |
|---|---|---|---|---|---|---|---|---|---|---|
| Production enclosure: HP MJF PA12, dyed black, vapor smoothed | none (process order: "MJF PA12 black, vapor smoothed"; HP 3D High Reusability PA 12) | HP Inc. / USA (powder reported from Evonik, Germany); printed by US bureaus | Tensile 48 MPa; modulus 1700-1800 MPa; elongation 20% XY, 15% Z; HDT 175 C at 0.45 MPa, 95-106 C at 1.82 MPa; density 1.01 g/cc; 80 um layers; min wall 0.5 (design 0.8); tolerance +/-0.3 mm or 0.3%; Ra 6-10 um blasted, 1-3 um smoothed | Top tub about dia 44 x 5.5-6; base plate about dia 40 x 0.8-1.5; bureau envelope about 284 x 380 x 380 | CAD upload, quote; 3-7 business days | Per shell 10-25 at 1; 3-6 at 100; 1.5-4 at 1000; smoothing +1-3 | Protolabs, Xometry (US-only option), Forecast 3D, Stratasys Direct, Endeavor 3D, DI Labs, RapidMade, Jawstec. Stock not applicable | Active | Agrees on all datasheet values, on the Protolabs tolerance wording and build size. Concern: vapor smoothing of walls under about 1 mm; Forecast 3D status uncertain; qty-1 price ignores order minimums | Recommended. UNVERIFIED |
| MJF PA12 GB (40% glass bead) | none (HP 3D HR PA 12 GB) | HP Inc. / USA | Tensile about 30 MPa; modulus 2500-2800 MPa; elongation 6.5-10%; HDT about 173 C at 0.45, 114-121 C at 1.82 MPa | Same parts | CAD upload | About 10-20% above PA12 | Protolabs, Xometry, Forecast 3D, Stratasys Direct | Active | Agrees | Viable (flat base plate). UNVERIFIED |
| MJF PA11 | none (HP 3D HR PA 11) | HP Inc. / USA (powder reported from Arkema, France) | Tensile about 52 MPa; modulus about 1800 MPa; elongation 50% XY, 35% Z; HDT 185 C at 0.45, 54 C at 1.82 MPa | Same parts | CAD upload | About 10-25% above PA12 | Protolabs, Xometry, Forecast 3D | Active | Agrees on properties. Doubts that Protolabs offers PA11 on MJF (recalls PA11 there as an SLS material) | Viable. UNVERIFIED |
| SLS PA12 (EOS PA 2200 / PA 650 class) | none | EOS / Germany; 3D Systems / USA; US bureaus | Tensile about 48 MPa; modulus 1650-1700 MPa; elongation 18% XY, 4-10% Z; min wall 0.7-1.0; tolerance +/-0.3 mm or 0.3%; Ra 8-12 um; white, dyeable | Same parts | CAD upload | MJF plus 10-30% | Protolabs, Xometry, Quickparts, Stratasys Direct, Fictiv | Active | Agrees on properties. Recalls Protolabs SLS tolerance as +/-0.010 in plus 0.0015 in/in (report says 0.001). White base powder is translucent at 0.6-0.8 mm | Fallback (second source), with light-leak precaution. UNVERIFIED |
| Carbon DLS EPX 82 | none (Carbon EPX 82 resin) | Carbon, Inc. / USA (Redwood City, CA) | Modulus about 2800 MPa; tensile about 82 MPa; elongation about 5.9%; HDT 125-130 C at 0.45 MPa; black; accuracy about +/-0.07 mm + 0.001 mm/mm; min wall 0.5 supported | Same parts | CAD upload; 5-10 business days | Per shell 40-100 at 1; 12-25 at 100; 6-12 at 1000 | Protolabs, Xometry, SyBridge, The Technology House, Dinsmore, Primary Manufacturing | Active (check for successor grades) | Agrees on properties and on Carbon's stated accuracy | Fallback (tight tolerance). UNVERIFIED |
| Carbon RPU 70; UMA 90 | none | Carbon, Inc. / USA | RPU 70: modulus about 1700 MPa, elongation about 100%, HDT about 60 C. UMA 90: HDT 45-50 C | Same parts | CAD upload | Not given | Carbon partner network | Active | Agrees | Rejected (HDT). UNVERIFIED |
| Prototype SLA: Formlabs Tough 2000; Rigid 4000 / 10K; Clear | none (resin cartridges; V2 names not confirmed) | Formlabs / USA (Somerville, MA) | Tough 2000: 46 MPa, 2.2 GPa, 48%, HDT 63 C at 0.45, 53 C at 1.82. Tough 1500: 33 MPa, 1.5 GPa, 51%, HDT 52 / 45 C. Rigid 10K: 65 MPa, 10 GPa, 1-2%, HDT 163 C (218 C after thermal cure). Clear: 65 MPa, 2.8 GPa, 6%, HDT 73 / 58 C | Same parts; Form 4 build about 200 x 125 x 210 | In-house printer, or service SLA | Resin 150-200 per litre; under 1 per shell set | Formlabs direct; DigiKey and resellers; service SLA at Protolabs, Xometry, Quickparts | Active (V1 vs V2 resin generations to check) | Agrees on all listed properties and on the Form 4 build volume. Recalls a 2025 Tough resin refresh; exact names unverified | Recommended for prototypes only. UNVERIFIED |
| Stratasys P3 with Loctite 3D 3843 or Somos WeatherX 100 | none | Stratasys / USA and Israel; Henkel / Germany | 3843: modulus about 1.8 GPa, elongation about 40%, HDT about 60 C. WeatherX 100: numbers not recalled | Same parts | CAD upload | Not given | Stratasys Direct; selected bureaus | Active | Agrees 3843 is an HDT-60 grade | Viable (quote only if weather-rated photopolymer wanted). UNVERIFIED |
| PolyJet Vero | none | Stratasys / USA and Israel | HDT 45-50 C; Tg 52-54 C | Same parts | CAD upload | 30-80 per shell at 1 | Protolabs, Xometry, Stratasys Direct, Fictiv | Active | Agrees | Rejected (HDT, UV). UNVERIFIED |
| FDM ASA / PETG | none | any FDM | ASA HDT about 98 C; walls 0.8 or more; +/-0.2-0.5 mm | Same parts | In-house | Cents | In-house; Xometry; Slant 3D | Active | Agrees | Viable (fit checks only) |
| Display and base seal: 3M VHB 5906 / 5907 / 5909 | 3M VHB Tape 5907 (0.20 mm); 5909 (0.30 mm); 5906 (0.15 mm) | 3M / USA (St. Paul, MN) | Black conformable acrylic foam, modified acrylic adhesive; land width 1.5-2.0 mm on printed parts; full strength after about 72 h; Primer 94 on PA12 | Ring about 35.0 OD x 31.5 ID x 0.2-0.3 (display); about 40 OD x 36 ID (base) | Die-cut by a converter, or laser / knife cut | 0.15-0.50 per ring at 1000; tooling 200-600 | Converters: Marian, Boyd, Strouse, JBC Technologies, Can-Do National Tape, CGR Products. Rolls: DigiKey, Mouser, R.S. Hughes. Stock not checked | Active | Agrees on the thickness of each grade and on the family description. Base ring must be reshaped to exclude screw holes | Recommended. UNVERIFIED |
| Thin PSA: 3M 9474LE (300LSE) | 3M 9474LE (also 9471LE, 9472LE) | 3M / USA | 300LSE acrylic on PET carrier, about 0.17 mm; 9471LE about 0.06 mm; 9472LE about 0.13 mm | Same ring geometry | Die-cut | Not given | Same converters and distributors | Active | Agrees on thicknesses | Viable (labels, vent, battery; not the main seal). UNVERIFIED |
| Camera-window adhesive: Loctite AA 3921 / AA 3926 | LOCTITE AA 3921; LOCTITE AA 3926 (Dymax grade not named) | Henkel / Germany (US operations in CT); Dymax / USA (Torrington, CT) | Light-cure acrylics; 3921 about 150 cP, 3926 about 5500 cP; fluorescent; cure at 365-405 nm | Bond land 0.5-0.75 wide; bond line 0.05-0.1 | Syringe dispense, flood cure | 40-80 per 25 ml | DigiKey, Ellsworth Adhesives, Krayden, R.S. Hughes. Stock not checked | Active | Agrees on viscosities; recalls these as medical-device grades. Adhesion to vapor-smoothed PA12 is untested | Recommended, subject to adhesion test. UNVERIFIED |
| O-ring, AS568-029 | Parker 2-029 plus compound (N0674-70, V0747-75, E0540-80, S0604-70) | Parker Hannifin / USA (Cleveland, OH) | ID 1.489 +/-0.013 in; CS 0.070 +/-0.003 in; gland per Parker: face depth 0.050-0.054 in, width 0.101-0.107 in; radial depth 0.050-0.052 in, width 0.093-0.098 in | 37.82 ID x 1.78 CS (OD 41.38) | Standard part | 0.10-0.60 | McMaster-Carr (series 9452K, 9464K, 9396K, 9557K, 9262K; dash-size suffix not confirmed); Parker distributors; Apple Rubber | Active | Agrees on AS568 sizes, Parker gland dimensions and compound codes. Radial gland needs about 4.0 mm of rim height, not 2.6 | Viable only with the DLS fallback. UNVERIFIED |
| Closure screws: M1.4 / M1.6 thread-forming for plastics | NOT GIVEN | EJOT / Germany; J.I. Morris / USA (Southbridge, MA); US Micro Screw / USA (Seattle, WA) | Pilot 0.75-0.80 x d (1.05-1.12 for M1.4); boss OD 3.5; engagement 2.8; 5-10 reassemblies | M1.4 x 4-5, head about dia 2.5 x 0.9 | Driven into printed bosses | 0.03-0.15 at 1000+ | US Micro Screw; J.I. Morris; Bossard; McMaster-Carr below M2 not confirmed | Active commodity | Arithmetic correct. Makers exist by recollection. No part number means this line is not orderable yet | Recommended in principle; part number OPEN. UNVERIFIED |
| Threaded inserts M1.0-M1.6 | PEM microPEM MSIB series (ordering code not given); McMaster 94180A series for M2 and up (94180A331 = M3; 94180A312 = M2, low confidence) | PennEngineering / USA (Danboro, PA); McMaster-Carr / USA (Elmhurst, IL) | Brass heat-stake inserts; boss OD at least 2 x insert OD | M1.4 insert OD about 2.3-2.5; boss 4.5-5 | Heat staking | 0.10-0.30 | PEM distributors (D.B. Roberts, Bisco); McMaster-Carr | Active | Recalls MSIB as a real microPEM family and 94180A as McMaster's tapered heat-set family; sizes not confirmed | Fallback (only if frequent re-opening is required). UNVERIFIED |
| Snap fits in PA12 | n/a | design feature | Strain 3-4% single use, 1.5-2% repeated; undercut 0.3-0.5 | n/a | n/a | n/a | n/a | n/a | Reasonable | Viable as locators only |
| Vent: adhesive ePTFE membrane | NOT CONFIRMED (Gore "VE8" adhesive series; smallest recalled by first report as VE80205) | W. L. Gore & Associates / USA (Newark, DE) | Oleophobic ePTFE on adhesive ring; IP67 / IP68; tens of ml/min at 70 mbar | About dia 5 x 0.2 | Adhesive, over a 1 mm hole | 0.30-1.00 at 1000+ | Gore distributors; alternate Donaldson; DigiKey / Mouser stocking not confirmed | Active | Recalls Gore adhesive vent series with numbering of this style; cannot confirm this exact number, its size, airflow or water-entry pressure | Recommended in principle; part number OPEN. UNVERIFIED |
| Ultrasonic welding | n/a | n/a | Not applicable to thermosets; unreliable on printed PA12; MEMS damage risk | n/a | n/a | n/a | n/a | n/a | Agrees; MEMS makers warn against ultrasonic exposure | Rejected |
| Conformal coating | NOT CONFIRMED (HumiSeal 1B31; Dowsil 1-2577; parylene by SCS) | HumiSeal (Chase) / USA; Dow / USA; SCS / USA | 25-75 um film; mask connectors and test pads | Film | Spray / dip / vapor | Not given | DigiKey; Ellsworth; SCS | Active | These products exist by recollection | Viable. UNVERIFIED |
| Battery swelling pad | NOT CONFIRMED (Rogers PORON 4701 / 4790 class) | Rogers Corporation / USA (Chandler, AZ) | Reserve 8-10% of cell thickness, 0.3 mm minimum | 0.3-0.5 foam | Die-cut | Not given | DigiKey; converters | Active | Agrees | Viable. UNVERIFIED |
| Camera window: sapphire, AR inside | NOT GIVEN (no stock number retrieved) | Edmund Optics / USA (Barrington, NJ); Swiss Jewel / USA (Philadelphia, PA); Meller Optics / USA; Guild Optical / USA; Thorlabs / USA (Newton, NJ) | Mohs 9; n about 1.77; 7.7% reflection per uncoated face | Dia 4.0-5.0 x 0.5-1.0 | Bonded into rim pocket | 25-45 at 1 (Edmund); 5-15 (Swiss Jewel); 1.5-4 at 2000 custom | Direct from the makers. Stock not checked | Stock catalogue items; custom 4-8 weeks | Physics agrees. Does not know a stock number at this size. Sapphire is birefringent (irrelevant here) | Recommended in principle; part number OPEN. UNVERIFIED |
| Camera window alternate: AR-coated N-BK7 or Gorilla Glass | NOT GIVEN | Edmund Optics / USA; Thorlabs / USA | N-BK7 n 1.517, about 4% per face uncoated | Dia 5 x 1.0 | Bonded | 20-35 at 1 | Edmund Optics; Thorlabs | Stock | Physics agrees (4.2% per face) | Fallback (prototypes). UNVERIFIED |
| Display cover, prototype: flat mineral-glass watch crystal | NOT GIVEN (ordered by size) | Sternkreuz / Germany and house brands; sold by US watch-material houses | 1.0 / 1.5 / 2.0 mm thick; diameters in 0.1 mm steps | Dia 35.0 x 1.0 (placeholder diameter) | Tape-bonded | Mineral 2-5; sapphire 15-30 | Esslinger (St. Paul, MN); Otto Frei (Oakland, CA); Cas-Ker (Cincinnati, OH); Jules Borel (Kansas City, MO). Stock not checked | Commodity | Agrees such crystals are sold in 0.1 mm steps. Strength of 1.0 mm mineral glass is not adequate unsupported | Recommended for prototypes only. UNVERIFIED |
| Display cover, production: custom strengthened glass disc | custom drawing | Abrisa Technologies / USA (Santa Paula, CA); Swift Glass / USA (NY); S.I. Howard Glass / USA (MA); Cat-i Glass / USA (IL); Precision Glass & Optics / USA (CA) | Chemically strengthened aluminosilicate; black printed border about 1.75 wide; AF coating; optional AR inside | Dia 35.0 x 0.7-1.1 (placeholder diameter) | Tape-bonded; custom order | 5-15 at 1000; NRE 500-2000; 4-8 weeks | Direct | Custom | Agrees these are US glass fabricators | Recommended for production. UNVERIFIED |
| Display cover: cast acrylic; polycarbonate | NOT CONFIRMED (McMaster 8560K series recalled) | SendCutSend / USA; Ponoko / USA; McMaster-Carr / USA | Acrylic n 1.49, isotropic, scratches; PC birefringent, attacked by sunscreen | Dia 35 x 1.0-1.5 | Laser cut | 1-5 | SendCutSend; Ponoko; McMaster-Carr | Commodity | Agrees | Acrylic viable for first prototypes; polycarbonate rejected |
| Hydrophobic / oleophobic coating | NOT CONFIRMED (Aculon; Cytonix FluoroPel) | Aculon / USA (San Diego, CA); Cytonix / USA (Beltsville, MD) | Contact angle 110-115 degrees; wears with abrasion | Nanometre film | Wipe / dip | Not given | Direct | Active; PFAS regulation a watch item | Agrees | Viable. UNVERIFIED |
| OSH Park 4-layer prototype service | n/a (service) | OSH Park / USA (Oregon) | FR408-HR; 1.6 mm only; 1 oz outer, 0.5 oz inner; ENIG; 5/5 mil; 10 mil drill; 4 mil annular ring; 15 mil copper to edge | Board dia 38 in a 38 x 38 box (2.24 sq in); 1.6 thick | Gerber / KiCad upload; no NRE | 10 per sq in for 3 copies: about 22 for three boards | oshpark.com | Active | Agrees on every listed spec and price. Recalls a newer 6-layer service; thickness options not recalled | Viable for electrical spins only. UNVERIFIED |
| AdvancedPCB (formerly Advanced Circuits) | n/a (service) | AdvancedPCB / USA (Aurora, CO) | Standard 5/5 mil, 10 mil drill; 0.8 mm available; ENIG; in-house assembly | Dia 38 x 0.8, 4 layers | Gerber / ODB++; quote | 300-600 for 10-25 boards at 5 days; 3-6 each at 1000 | 4pcb.com | Active; ownership (APCT combination) to confirm | Agrees on the rebrand; recalls an AdvancedPCB / APCT merger announcement | Recommended. UNVERIFIED |
| Bay Area Circuits | n/a (service) | Bay Area Circuits / USA (Fremont, CA) | Quick-turn rigid fab; about 4/4 mil; 0.031 in 4-layer | Dia 38 x 0.8 | Online quote | 200-400 small lot | bayareacircuits.com | Active | Agrees it is a Fremont bare-board fab | Fallback (bare boards). UNVERIFIED |
| Sierra Circuits; Royal Circuits (Summit Interconnect) | n/a (service) | Sierra Circuits / USA (Sunnyvale, CA); Summit Interconnect / USA | HDI capable; 1-5 day turns | Dia 38 x 0.8 | Online quote | 500-1500 small lot | Direct | Active | Agrees | Viable (only if HDI is forced). UNVERIFIED |
| MacroFab | n/a (service) | MacroFab / USA (Houston, TX) | Turnkey; Houston line plus North American partner factories | n/a | BOM + placement upload | Assembly 8-20 per board at 100; 4-8 at 1000 | macrofab.com | Active | Agrees, including the Mexico partner caveat | Viable with written US-only confirmation. UNVERIFIED |
| Screaming Circuits; CircuitHub / Worthington Assembly | n/a (service) | Screaming Circuits (Milwaukee Electronics) / USA (Canby, OR); CircuitHub / USA (South Deerfield, MA) | Quick-turn prototype assembly; 0201 and 0.4 mm pitch | n/a | Kitted or turnkey | 700-1500 for 5-10 boards | Direct | Active; status to confirm | Agrees | Fallback (prototype assembly). UNVERIFIED |
| Programming / test access | TC2030-IDC-NL; TC2030-CTX-NL; Mill-Max 09xx or QA Technology probes (probe PN not given) | Tag-Connect / USA; Mill-Max / USA (Oyster Bay, NY); QA Technology / USA (Hampton, NH) | 6 pads at 1.27 mm pitch plus 3 alignment holes; no board connector | Footprint about 3.5 x 6.5 (to verify) | SWD | Cable 35-45; fixture 1.5-5k | DigiKey; Tag-Connect direct. Stock not checked | Active | Recalls both Tag-Connect order codes as real products | Recommended. UNVERIFIED |
| Tilt / camera calibration station | Starrett 199Z level; granite plate; kinematic nest; thermal chamber; targets | L.S. Starrett / USA and others | Level sensitivity 0.0005 in per ft per division (42 urad) | Bench about 600 x 450 plus 3 m lane | n/a | 3-8k without chamber | McMaster-Carr; MSC; Thorlabs; Newport; TestEquity | Active | Arithmetic confirmed; recalls the same sensitivity. Needs five or more temperature points | Recommended, with that change. UNVERIFIED |
| Grain-sensor calibration target | NOT CONFIRMED (Labsphere Spectralon SRS-99 / SRT-99 family) | Labsphere / USA (North Sutton, NH; parent Halma, UK) | Lambertian standard; per-LED gain so first harmonic is zero | Target dia 30-50 | n/a | 300-600; PTFE sheet a few dollars | Labsphere direct; Edmund Optics; McMaster-Carr | Active | Recalls SRS-99 and SRT-99 as real Labsphere families | Recommended. UNVERIFIED |
| IP67 production leak tester | NOT CONFIRMED (Cincinnati Test Systems Sentinel class; Uson) | Cincinnati Test Systems / USA (OH); Uson / USA (Houston, TX); InterTech / USA (Skokie, IL) | Chamber pressure-decay test; IPX7 is 1 m for 30 min | Cavity about dia 46 x 9 | n/a | 8-20k | Direct | Active | Agrees on IPX7 definition and that these makers exist | Viable (dunk test first). UNVERIFIED |

## 4. Key findings, with confidence

Confidence here means confidence after this pass. "High" is given only to results that were recomputed or follow from basic physics.

1. **No vendor fact was verified online by either pass.** Confidence: high.
2. **MJF PA12 is the most suitable production process.** The logic (ductile, high HDT at low load, many interchangeable US bureaus, low cost) is sound and the recalled properties agree with the reviewer's recollection. Open points: vapor-smoothing wall limit, thin-disc warp, opacity, powder removal from small blind holes. Confidence: medium on the choice, low on every number.
3. **Low-HDT photopolymers should not ship.** The 60-70 C case is plausible: a steady-state energy balance for a black disc at 1000 W/m2 gives about 55-77 C with a light breeze (30-40 C ambient) and 85-92 C in still air on an insulating surface (reviewer estimate). The recalled HDT values agree with reviewer recollection. Confidence: medium.
4. **A bonded seal is the right architecture.** The tolerance argument is valid for a radial gland (two mating diameters) and weaker for a face gland (one groove depth). The space argument is decisive: a 1.78 mm O-ring needs a 2.6 mm wide face groove plus walls (about 4.2 mm of radius) or a 2.4 mm radial groove plus lands (about 4.0 mm of rim height). Confidence: medium-high.
5. **A vent is needed, and the loads are larger than stated.** Recomputed: +17.28 kPa for 20 to 70 C; 13.5-15.0 N on the display bond depending on where the seal line is taken; mean tensile stress on a 35/31.5 mm tape ring about 74 kPa. At 2,000 m altitude a unit sealed at sea level sees +21.8 kPa at 20 C and +39 kPa at 70 C (31 N). By reviewer recollection, 3M's rule for sustained static load on VHB is about 4 square inches of tape per pound, which this joint misses by a factor of about 40. Confidence: high on the pressures, low on the 3M rule (UNVERIFIED).
6. **The vent does not protect against a hot-unit dunk.** See section 1. Confidence: high (physics).
7. **Ultrasonic welding should not be used.** Thermosets cannot be welded; MEMS exposure is a recognised risk. Confidence: medium.
8. **Thread-forming screws into PA12 are the practical fastener at M1.4.** Arithmetic confirmed. No part number exists yet. Confidence: medium on the approach, none on the part.
9. **Sapphire for the camera windows.** Hardness argument is sound; Fresnel loss recomputed at 7.73% per face, 14.9% for two faces. No stock part identified. Confidence: medium on the choice, none on the part.
10. **Glass for the display cover.** Sound. The first report's statement that sapphire is not birefringent is wrong. The unsupported 1.0 mm cover is at risk under a step load. The LCD's own polariser is a separate sunglasses problem. Confidence: medium-high.
11. **OSH Park 4-layer is 1.6 mm only.** Agrees with reviewer recollection; UNVERIFIED. Cost arithmetic confirmed (2.238 sq in; about 22 USD and 11 USD if the recalled prices are right). Confidence: low-medium.
12. **Common-denominator PCB rule set.** Internally consistent (5 mil annular ring from a 10 mil drill and 20 mil pad exceeds the recalled 4 mil minimum). Caveat: stack-up differs between 1.6 mm and 0.8 mm boards. Confidence: medium.
13. **The printed shell cannot be the metrology reference.** Recomputed: 0.3 mrad over 33 mm is 9.9 um; 100-150 ppm/K over 40 K and 33 mm is 132-198 um. Confidence: high on the arithmetic; the CTE input is UNVERIFIED but typical.
14. **Calibration with inexpensive metrology is feasible.** Recomputed: 0.0005 in per ft is 41.7 urad; 25 um over 127 mm is 0.197 mrad. Needs more temperature points and hard seating points. Confidence: medium.
15. **Cost estimates.** The first report's own estimates. Qty-1 figures probably ignore bureau order minimums. Confidence: low.
16. **Vendor status changes.** Mostly agree with reviewer recollection; none confirmed. Confidence: low.

## 5. Verification table

Verdict key: confirmed = recomputed or logically checked here; corrected = the report's value or wording needs changing; contradicted = evidence found against it; unverifiable = needs a live source that could not be reached in this pass.

### 5a. Derivations and numeric claims that could be checked without the web

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | Sealed at 20 C, heated to 70 C: +17.3 kPa; 13.9 N on a dia 32 mm window | confirmed | 17.28 kPa; 13.9 N on dia 32.0; 13.5 N on the 31.5 mm tape ID; 15.0 N at the tape mid-line (33.25 mm) | Ideal gas at constant volume, 101.325 kPa x 50 / 293.15. |
| 2 | Hot puck at 60 C quenched to 15 C: -13.7 kPa, plus 9.8 kPa for 1 m of water, total about 23.5 kPa | corrected | -13.69 kPa only if the internal air was at ambient pressure at 60 C (vented or leaky unit). A unit perfectly sealed at 20 C sees -1.73 kPa at 15 C (11.5 kPa with 1 m of water). From 70 C the total is 26.0 kPa. Hydrostatic term 9.79 kPa | The arithmetic is right; the stated condition was missing. |
| 3 | "A vent is needed" because of the above | corrected | The vent removes the sustained outward load in air. It does not remove the quench vacuum: a submerged membrane passes no air, so a vented unit sees the full 23.5-26 kPa inward. Vent water-entry pressure and all seals must be specified for at least 25 kPa with margin (suggest 50 kPa) | Conclusion (fit a vent) stands; the reasoning for the dunk case was reversed. |
| 4 | Pressure cases not considered: altitude | corrected | Sealed at sea level and 20 C: +21.8 kPa at 2,000 m; +39.1 kPa at 2,000 m and 70 C (31.5 N on dia 32); +26.1 kPa in a 75 kPa aircraft hold | Reviewer addition, standard-atmosphere formula. Strengthens the case for a vent. |
| 5 | Load on the tape ring is acceptable only with a vent | confirmed | Ring 35.0 / 31.5 mm has 183 mm2; 13.5 N gives 74 kPa (10.7 psi) mean tension | The comparison with a 3M static-load rule (about 0.25 psi sustained) is reviewer recollection, UNVERIFIED. |
| 6 | 0.3 mrad over a 33 mm baseline is 10 um | confirmed | 9.9 um | - |
| 7 | PA12 at 100-150 ppm/K moves a 33 mm span 130-200 um over 40 K | confirmed (arithmetic) | 132-198 um | CTE input UNVERIFIED; typical for PA12 by recollection. |
| 8 | 6.5 mm chord flat on a 44 mm rim has 0.24 mm sagitta | confirmed | 0.241 mm (0.253 mm on a 42 mm rim) | - |
| 9 | Internal height 4.9-5.4 mm limits the camera window to about 4.0-4.5 mm | corrected | Arithmetic right (6.5-7.0 minus 2 x 0.8). But the window sits in the rim, which is full height. A 5.0 mm window leaves 0.75-1.0 mm of material above and below in a 6.5-7.0 mm rim | Limit is set by the base-plate split line and the camera module, not the cavity height. |
| 10 | Required window clear aperture | corrected | Clear aperture = 2 x (r_aperture + d x tan(half-FOV)). Examples: r 0.5 mm, d 1.0 mm, 30 degrees: 2.2 mm. r 0.75, d 1.5, 35 degrees: 3.6 mm. r 1.0, d 1.5, 35 degrees: 4.1 mm | A 4.0 mm window (3.0 mm clear) is marginal; depends on the chosen camera. |
| 11 | Sapphire n about 1.77: 7.7% per uncoated face, about 15% for both | confirmed | 7.73%; 14.9% | Refractive index is a textbook value. |
| 12 | N-BK7: about 4% per face | confirmed | 4.22% at n = 1.517 | - |
| 13 | AS568-029 is 1.489 in ID x 0.070 in CS = 37.82 x 1.78 mm, OD 41.38 | confirmed (conversion) | 37.82 x 1.778 mm, OD 41.38; -028 = 34.65, -030 = 41.00 | The inch values match reviewer recollection of AS568; standard not opened. |
| 14 | Parker gland dimensions for 0.070 in CS | unverifiable | - | UNVERIFIED. Matches reviewer recollection of the Parker O-Ring Handbook design charts. Conversions: face 1.27-1.37 deep x 2.57-2.72 wide; radial 1.27-1.32 deep x 2.36-2.49 wide; squeeze 23-29% nominal. |
| 15 | O-ring costs "about 3 mm of radius and about 2.6 mm of height" | corrected | Radial gland: 2.9-3.0 mm of radius and about 4.0 mm of rim height (2.36-2.49 groove plus two 0.8 mm lands). Face gland: about 4.2 mm of radius (2.6 groove plus two walls) and about 2.1 mm of height | The 2.6 mm figure is the face-groove width, which is a radial dimension. |
| 16 | MJF tolerance can consume the whole squeeze of a 1.0 mm CS O-ring | confirmed for a radial gland | Overstated for a face gland, where squeeze depends on one groove depth and a hard stop | Worst-case stack of two diameters at +/-0.2-0.3 mm is +/-0.2-0.3 mm radial against 0.25-0.30 mm squeeze. |
| 17 | Starrett 199Z: 0.0005 in per ft per division is 42 urad | confirmed (conversion) | 41.7 urad (8.6 arc-seconds) | Sensitivity value matches reviewer recollection; UNVERIFIED. |
| 18 | 25 um gauge-block step over 127 mm is 0.2 mrad | confirmed | 0.197 mrad | - |
| 19 | 640 pixels over 60 degrees is 1.6 mrad per pixel; 0.3 mrad is about 0.2 pixel | corrected | 1.64 mrad/px average; 1.80 mrad/px at the centre of a rectilinear lens; 0.3 mrad is 0.17-0.18 px | Small change; conclusion (sub-pixel targets needed) stands. |
| 20 | 38 x 38 mm is 2.24 sq in; about 22 USD and 11 USD for three boards | confirmed (arithmetic) | 2.238 sq in; 22.38 and 11.19 USD | Price-per-area inputs UNVERIFIED. |
| 21 | M1.4 screw rules: boss 3.5, pilot 1.05-1.12, engagement 2.8 mm | confirmed (arithmetic) | - | Rules of thumb UNVERIFIED. Addition: a blind 1.1 mm x 3 mm hole may not clear of powder; use through-holes or drill. |
| 22 | A dark puck reaches 60-70 C in sun | confirmed as plausible | 57-77 C with a 15-25 W/m2K breeze at 30-40 C ambient and no heat loss to the turf (50-66 C with it); 85-92 C in still air with an insulated back | Reviewer energy-balance estimate (absorptance 0.9, 1000 W/m2), not a measurement. |
| 23 | Three-temperature soak (5 / 25 / 50 C) for the compensation table | corrected | Five or more temperatures, or a slow ramp up and down; validate on points not used in the fit | Same correction as `inertial-sensors.md`. |
| 24 | A stepped-on 1.0 mm cover over a 32 mm span can crack | confirmed | Plate bending: 400-800 N on the puck gives about 50-100 MPa (clamped edge) to 80-160 MPa (simply supported) on the glass if unsupported | Conservative (rigid rim, load share by area). Ordinary glass is not safe at these stresses; chemically strengthened glass with support is. |
| 25 | Unsupported 0.8 mm PA12 base plate under pressure | corrected (addition) | 17.3 kPa over an 18 mm radius: 0.33 mm (clamped) to 1.27 mm (simply supported) at 1700 MPa; double at 70 C | Not in the first report. Base and cover need internal support; deflection also moves the seating plane. |
| 26 | "Glass, sapphire and cast acrylic are not birefringent" | corrected | Sapphire is birefringent (index difference about 0.008; about 8 um retardance per mm off the c-plane) | Textbook crystal optics; no URL retrieved in this session. Irrelevant for camera windows; relevant only if sapphire were used over the display. |
| 27 | Polycarbonate cover rejected because of polarised sunglasses | confirmed (physics) | Additional issue: the memory LCD's own polariser makes brightness vary as cos-squared of marker rotation, whatever the cover | Needs a decision in the display workstream. |
| 28 | Screws "3-4 M1.4 into PA12" with a 40/36 mm tape ring | corrected (addition) | Screw holes must be outside the sealed boundary: tape pattern loops inside each boss, or each screw is sealed | Not in the first report; without it the base seal leaks through the screw holes. |

### 5b. Recommended and fallback candidates: existence, status, availability

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 29 | MJF PA12 black with vapor smoothing is offered by the named US bureaus | unverifiable | - | UNVERIFIED. Reviewer recollection: a mainstream offering at Protolabs and Xometry. |
| 30 | HP PA12 datasheet values (48 MPa; 1700-1800 MPa; 20% / 15%; HDT 175 C at 0.45 MPa, 95-106 C at 1.82 MPa; 1.01 g/cc) | unverifiable | - | UNVERIFIED. All match reviewer recollection of the HP datasheet. |
| 31 | MJF design rules: min feature 0.5 mm; +/-0.3 mm or 0.3% (Protolabs +/-0.012 in plus 0.002 in/in); envelope 284 x 380 x 380 mm; 80 um layers | unverifiable | - | UNVERIFIED. Matches reviewer recollection. |
| 32 | Vapor smoothing gives Ra 1-3 um and is suitable for 0.6-0.8 mm walls | unverifiable | - | UNVERIFIED. Reviewer recollection is that some bureaus ask for about 1 mm minimum for vapor smoothing. Decision-critical. |
| 33 | PA12 GB and PA11 properties | unverifiable | - | UNVERIFIED. Match reviewer recollection. PA11 on MJF at Protolabs is doubtful. |
| 34 | SLS PA12 properties and tolerance | unverifiable | Reviewer recalls Protolabs SLS as +/-0.010 in plus 0.0015 in/in | UNVERIFIED either way. |
| 35 | Carbon EPX 82: 2800 MPa, 82 MPa, 5.9%, HDT 125-130 C; accuracy +/-0.07 mm + 0.001 mm/mm; still active | unverifiable | - | UNVERIFIED. Matches reviewer recollection. Lifecycle not known after mid-2026. |
| 36 | HDT of rejected resins (RPU 70 about 60 C; UMA 90 45-50 C; Tough 2000 63 C; Tough 1500 52 C; Vero 45-50 C; 3843 about 60 C) | unverifiable | - | UNVERIFIED. All match reviewer recollection. |
| 37 | Formlabs resin data and Form 4 build volume | unverifiable | - | UNVERIFIED. Match reviewer recollection. Current resin generation names not confirmed. |
| 38 | 3M VHB 5906 / 5907 / 5909 thickness 0.15 / 0.20 / 0.30 mm; active; sold as rolls by DigiKey / Mouser / R.S. Hughes | unverifiable | - | UNVERIFIED. Thicknesses match reviewer recollection. |
| 39 | 3M 9474LE / 9471LE / 9472LE thickness | unverifiable | - | UNVERIFIED. Match reviewer recollection. |
| 40 | Loctite AA 3921 (about 150 cP) and AA 3926 (about 5500 cP), active, US distribution | unverifiable | - | UNVERIFIED. Viscosities match reviewer recollection. |
| 41 | M1.4 / M1.6 thread-forming screws: exact MPN, US stock | unverifiable | - | No MPN was given. OPEN bill-of-materials line. |
| 42 | PEM microPEM MSIB (M1.0-M1.6); McMaster 94180A331 = M3, 94180A312 = M2 | unverifiable | - | UNVERIFIED. Family names match reviewer recollection; sizes and codes not confirmed. |
| 43 | Gore adhesive vent VE80205, about dia 5 x 0.2 mm, IP67 / IP68 | unverifiable | - | UNVERIFIED. Exact number, size, airflow, water-entry pressure and US stock all unknown. OPEN bill-of-materials line. |
| 44 | Sapphire window dia 4-5 x 0.5-1.0 mm: stock number, AR option, price | unverifiable | - | No MPN was given. OPEN bill-of-materials line. |
| 45 | N-BK7 / Gorilla Glass dia 5 x 1 mm windows from Edmund / Thorlabs | unverifiable | - | No MPN was given. |
| 46 | Flat mineral crystals, 1.0 mm, 0.1 mm diameter steps, from Esslinger / Otto Frei / Cas-Ker / Jules Borel at 2-5 USD | unverifiable | - | UNVERIFIED. Plausible by reviewer recollection. |
| 47 | US glass fabricators for the production cover (Abrisa and others) | unverifiable | - | UNVERIFIED. Company locations match reviewer recollection. |
| 48 | US 3D-print bureau list and status | unverifiable | - | UNVERIFIED. Reviewer has a weak, unconfirmed recollection of 2025 reports that Forecast 3D was being wound down. Confirm before listing it. |
| 49 | OSH Park 4-layer: 1.6 mm only, FR408-HR, 5/5 mil, 10 mil drill, 4 mil ring, 10 USD per sq in for three | unverifiable | - | UNVERIFIED. Matches reviewer recollection. Decision-critical. |
| 50 | AdvancedPCB offers 0.8 mm 4-layer with in-house US assembly | unverifiable | - | UNVERIFIED. |
| 51 | Bay Area Circuits; Screaming Circuits; CircuitHub: capability and current status | unverifiable | - | UNVERIFIED. |
| 52 | Tag-Connect TC2030-IDC-NL and TC2030-CTX-NL exist and are stocked by DigiKey | unverifiable | - | UNVERIFIED. Both order codes match reviewer recollection. |
| 53 | Labsphere Spectralon SRS-99 / SRT-99 | unverifiable | - | UNVERIFIED. Family names match reviewer recollection. |
| 54 | McMaster series numbers (9452K, 9464K, 9396K, 9557K, 9262K, 8560K) and Parker compound codes | unverifiable | - | UNVERIFIED. Match reviewer recollection. |
| 55 | Vendor status: Shapeways (Chapter 7 in 2024, relaunched as a Dutch company), Fictiv (MISUMI, 2025), Hubs (Protolabs Network), Fast Radius (SyBridge), Tempo Automation (closed 2023), Royal Circuits (Summit, 2021), AdvancedPCB / APCT, Sunstone (American Standard Circuits) | unverifiable | - | UNVERIFIED. Each matches reviewer recollection. |
| 56 | 3M exit from PFAS manufacturing by end of 2025 (Novec coatings) | unverifiable | - | UNVERIFIED. Matches reviewer recollection of the December 2022 announcement. |
| 57 | Enclosure cost estimates (MJF set 20-50 at 1; 6-12 at 100; 4-10 at 1000; DLS about 3x) | unverifiable | - | First report's own estimates. Need quotes. |

## 6. Corrections to carry into the design

1. Specify the vent for water-entry pressure of 50 kPa or more, and qualify all seals at 25 kPa inward (hot unit into cold water at 1 m) as well as at the sustained outward case.
2. Add altitude and air freight to the pressure cases: up to about 40 kPa outward if the vent is blocked.
3. Route the base tape so every screw hole is outside the sealed zone, or seal each screw.
4. Support the display cover and the base plate internally; no unsupported span above about 15 mm.
5. Production display cover in chemically strengthened glass. Do not use sapphire over the display unless it is c-plane. Mineral crystal for prototypes only.
6. Add a polarised-sunglasses requirement to the display specification (quarter-wave film, fixed orientation, or a display without a polariser).
7. Confirm the bureau's minimum wall for vapor smoothing before freezing 0.6-0.8 mm walls; budget 0.4 mm of extra thickness if 1.0 mm is required.
8. Three hard seating inserts in the base; cameras and precision accelerometer on one rigid board on three mounting points.
9. Size the camera window from the selected camera module; default to 5.0 x 0.5 mm.
10. Print screw pilots as through-holes or drill them after printing.
11. SLS second source only with a black or grey base powder or an internal opaque coat; test light leakage in both processes in visible and near-infrared.
12. Temperature calibration at five or more points or with a ramp.
13. Do the radio check and any impedance-sensitive routing on the real 0.8 mm stack-up, not on a 1.6 mm OSH Park board.
14. If the O-ring fallback is ever used, allow about 4 mm of rim height for a radial gland.

## 7. Risks

- **Nothing was web-verified in this pass or the previous one.** Recalled part numbers (Gore VE80205, McMaster 94180A312 and the O-ring series, Parker compound codes, Labsphere and Tag-Connect codes), all prices, lead times and vendor capabilities may be wrong or out of date. The reviewer's knowledge stops around mid-2026, about five months before the date of this document.
- **Four enclosure bill-of-materials lines have no part number:** closure screws, vent, camera windows, display crystal. "Ready to manufacture" cannot be claimed for the enclosure until they are closed.
- If OSH Park is assumed to supply the 0.8 mm 4-layer board and it does not, the prototype will not fit the stack.
- Thin MJF discs may warp 0.2-0.5 mm and vary by +/-0.2-0.3 mm; bond lands narrower than about 1.5 mm will give inconsistent IP67 yield.
- Vapor smoothing may distort 0.6-0.8 mm walls or may not be offered for them.
- PA12 creeps above its glass transition (about 40-50 C by recollection). A blocked vent puts 74 kPa or more of sustained tension on the display tape at 70 C.
- A hot unit dropped in water puts about 25 kPa of vacuum on every seal even with a working vent.
- Screw holes inside the sealed zone would defeat the base seal.
- Thin walls may pass visible or near-infrared light into the cameras and the grain sensor, especially in white-powder SLS.
- The shell cannot hold camera-to-accelerometer alignment (10 um over 33 mm); thermal gradients through a printed puck bow it by roughly 1.5-2 mrad at the rim for 5 C through-thickness (estimate recorded in `inertial-sensors.md`, re-derived here as curvature = CTE x temperature difference / thickness).
- Assembly stress shifts the accelerometer offset; calibration before final closure is invalid.
- A stepped-on marker can crack an unsupported cover and collapse an unsupported 0.8 mm base.
- Sand, dew, clippings, fertiliser and sunscreen at turf level; hydrophobic coatings wear off.
- Polarised sunglasses can black out a polariser-based display at some marker rotations.
- Marketplace bureaus and assemblers may route work outside the US unless US-only production is specified in writing.
- PFAS regulation may affect fluorinated easy-clean coatings and ePTFE vents; keep an alternate vent source.
- The DLS epoxy fallback is brittle around small screw bosses and cannot take heat-set inserts; a late process switch forces a fastener redesign.
- A breathing vent lets humid air in; condensation inside the display or camera windows is possible after a warm, humid day followed by a cold morning.

## 8. Open questions

Items 1-8 need network access; the rest need tests or decisions.

1. OSH Park: current 4-layer thickness options, design rules, price, and whether a thin 4-layer or 6-layer service exists.
2. Exact stock numbers, AR options and prices for sapphire windows of 4-5 mm diameter and 0.5-1.0 mm thickness (Edmund Optics, Swiss Jewel, Thorlabs, Meller).
3. Exact Gore or Donaldson adhesive vent part number: outer diameter, thickness, airflow, water-entry pressure, adhesive temperature rating, US distributor stock.
4. Exact part numbers for M1.4 and M1.6 thread-forming screws for plastics from US vendors, and the PEM microPEM MSIB ordering codes.
5. Published MJF design rules and vapor-smoothing limits (minimum wall, dimensional change) at two US bureaus; whether each prints in the US.
6. HP PA12, Carbon EPX 82 and Formlabs datasheets: confirm the recalled values and current lifecycle.
7. Quotes at 1, 100 and 1000 for both shells in MJF PA12 (dyed, vapor smoothed) and in Carbon EPX 82 from at least two US bureaus.
8. Current status and ownership of Forecast 3D, AdvancedPCB / APCT, Screaming Circuits and CircuitHub / Worthington Assembly; whether MacroFab and CircuitHub will commit to US bare boards and US build sites.
9. Do vapor-smoothed 0.6-0.8 mm MJF PA12 coupons pass a 1 m, 30 minute immersion, a 25 kPa vacuum quench, and a light-leak test in visible and near-infrared?
10. Bond durability of the VHB ring and the light-cure acrylic on vapor-smoothed PA12 after heat and humidity ageing, thermal shock, sunscreen and insect repellent.
11. Which display and which camera module are selected? They set the cover diameter, the window size and the internal support layout.
12. How is the unit charged (sealed contacts or wireless coil)? This decides where the vent and any other penetrations go.
13. Does the grain sensor need a window in the base recess, and of what size?
14. Is the battery user-replaceable? If not, a permanently bonded base is thinner and more reliable.
15. Which hard insert and bonding method give the base seating points a reseating repeatability of a few micrometres?
16. How will the display stay readable through polarised sunglasses at any marker rotation?

## 9. Sources

No URL was successfully opened in this verification pass, and the first report cited none (it was written from memory). There is therefore no list of consulted web sources.

Attempted and failed in this pass (not sources; recorded for traceability):

1. https://docs.oshpark.com/services/four-layer/ - host did not resolve (outside allowed network domains).
2. https://www.protolabs.com/services/3d-printing/multi-jet-fusion/ - host did not resolve.
3. https://www.carbon3d.com/materials/epx-82 - host did not resolve.
4. https://www.edmundoptics.com/f/sapphire-windows/12435/ - host did not resolve.

The four addresses above were the reviewer's guesses at the relevant pages and were never loaded; they are not confirmed to exist.

Local material used:

5. The first research report (JSON supplied to this verification step by the workflow).
6. `greenline-marker/docs/research/inertial-sensors.md` in this repository (cross-checked for the temperature-calibration, hard-pad and thermal-bow points).
7. Reviewer calculations: ideal-gas pressure change, standard-atmosphere pressure, circular-plate bending (clamped and simply supported), Fresnel reflection at normal incidence, chord sagitta, unit conversions, and a single-node solar energy balance. Formulas and results are given in sections 4 and 5a.

Where to verify (sites to consult once network access is available; none was consulted): the vendor hosts listed at the end of section 0.
