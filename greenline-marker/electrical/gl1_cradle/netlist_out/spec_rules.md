| Spec rule | What the specification says | Where it is in the netlist | Result |
|---|---|---|---|
| board | cradle.pcb: 30.0 x 22.0, thickness 1.6; 2 layers (task) | outline rectangle about the board centre = marker (0, -23.2); layers 2 | pass |
| screws | four screw holes at cradle.pcb.screws [[-12.5, -31.5], [12.5, -31.5], [-12.5, -14.5], [12.5, -14.5]] | NPTH holes MH1-MH4 dia 2.2 (diameter PROVISIONAL) | pass |
| pin row | seven spring-pin positions on 2.54 mm pitch at pin_row_y -17.0, in the YAML order (VBUS, D-, D+, GND, SWDIO, SWCLK, NRST from x = -7.62 to +7.62 seen from above) | SP1-SP7 (through hole, top side): pad centres measured at marker x = [-7.62, -5.08, -2.54, 0.0, 2.54, 5.08, 7.62], y = [-17.0] | pass |
| fitted | four spring pins fitted (VBUS, D-, D+, GND) and three service positions (SWDIO, SWCLK, NRST) for the factory fixture | SP1-SP4 fitted, SP5-SP7 not fitted (same footprint, fitted in the factory fixture) | pass |
| service | (task) the three service positions taken to a small unpopulated header or test pads | J2: four bare pads on the bottom (GND, SWDIO, SWCLK, NRST) | pass |
| USB-C | USB-C receptacle (USB 2.0; YAML: GCT USB4105, rear exit), the USB mouth at the YAML edge (usb_mouth_y -35.5) | J1 USB4105-GF-A, top side, body front at marker y -35.50 (1.3 mm beyond the board edge); SBU1 / SBU2 not connected | pass |
| USB-C land | (KiCad DRC, rule set) 0.20 mm between a hole wall and foreign copper | J1 uses the project copy of KiCad's USB4105 land pattern: the four outer ground pads are 0.04 mm shorter; smallest distance from a locating-peg hole to a pad of J1 0.236 mm (library footprint: 0.194); one pad object per wide land instead of two coincident ones (B1 on A12, B12 on A1, B4 on A9, B9 on A4); the stored file equals the library file with exactly these changes *(DEVIATION from the maker's land pattern, PROVISIONAL; no design rule is relaxed. The merged pad objects are a workaround for the toolchain's router, which cannot join coincident pads; the copper is unchanged)* | **departure** |
| CC | 5.1 kohm from CC1 and from CC2 to ground | R1: CC1 (A5) - GND, R2: CC2 (B5) - GND, one resistor each | pass |
| fuse | a resettable fuse in VBUS (hold about 0.2 A, trip about 0.5 A, PROPOSED) | F1 between VBUS_IN (J1 lands A4 / B9 and A9 / B4) and VBUS (SP1): hold 200 mA, trip 500 mA (PROVISIONAL part MF-FSMF020X-2) | pass |
| ESD | USBLC6-2SC6 on VBUS / D+ / D- | U1: D- through pins 1 + 6, D+ through pins 3 + 4, pin 5 on VBUS_IN (C1 100n), pin 2 GND *(ADDED: C1 100 nF at the VBUS pin of U1; the clamp sits on the connector side of the fuse)* | pass |
| top side | nothing on the top side may reach the pocket ceiling (YAML note) | height limit 0.0 mm on the whole top side, J1 and SP1-SP7 exempt; every other part is on the bottom | pass |
| pin tables | (task) the pin -> pad table of every library-backed part agrees with a second source | U1 against the installed KiCad symbol USBLC6-2SC6, J1 against USB_C_Receptacle_USB2.0_16P (pad numbers and pin names): all agree *(the spring pins and the fuse have one or two interchangeable pads)* | pass |
| fiducials | (task) at least three global fiducials per side | FID1-FID3 top, FID4-FID6 bottom | pass |
| status | (task) every BOM part carries an evidence status | Part.fields['Status'] is RESEARCH or PROVISIONAL on all 13 BOM parts | pass |

14 rows: 13 pass, 1 departure (USB-C land), 0 open, 0 workaround, 0 FAIL
