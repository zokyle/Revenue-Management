| Spec rule | What the specification says | Where it is in the netlist | Test |
|---|---|---|---|
| board | cradle.pcb: 30.0 x 22.0, thickness 1.6; 2 layers (task) | outline rectangle about the board centre = marker (0, -23.2); layers 2 | pass |
| screws | four screw holes at cradle.pcb.screws [[-12.5, -31.5], [12.5, -31.5], [-12.5, -14.5], [12.5, -14.5]] | NPTH holes MH1-MH4 dia 2.2 (diameter PROVISIONAL) | pass |
| pin row | seven spring-pin positions on 2.54 mm pitch at pin_row_y -17.0, in the YAML order | SP1-SP7 (through hole, top side) at marker x = [-7.62, -5.08, -2.54, 0.0, 2.54, 5.08, 7.62] | pass |
| fitted | the four consumer pins populated (VBUS, D-, D+, GND); three service positions for the factory fixture | SP1-SP4 fitted, SP5-SP7 DNP (same footprint, fitted in the factory fixture) | pass |
| service | the three service positions taken to a small unpopulated header or test pads | J2: four bare pads on the bottom (GND, SWDIO, SWCLK, NRST) | pass |
| USB-C | USB-C receptacle (GCT USB4105 class, USB 2.0), the USB mouth at the YAML edge (usb_mouth_y -35.5) | J1 USB4105-GF-A, top side, body front at marker y -35.50 (1.3 mm beyond the board edge) | pass |
| CC | 5.1 kohm on CC1 and CC2 | R1: CC1 (A5) - GND, R2: CC2 (B5) - GND | pass |
| fuse | a resettable fuse in VBUS sized for the marker | F1 between VBUS_IN (J1 A4, A9, B4, B9) and VBUS (SP1): hold 100 mA, trip 300 mA (PROVISIONAL part) | pass |
| ESD | USBLC6-2SC6 | U1: D- through pins 1 + 6, D+ through pins 3 + 4, pin 5 on VBUS_IN (C1 100n), pin 2 GND | pass |
| top side | nothing on the top side may reach the pocket ceiling (YAML note) | height limit 0.0 mm on the whole top side, J1 and SP1-SP7 exempt; every other part is on the bottom | pass |
| fiducials | (task) at least three global fiducials per side | FID1-FID3 top, FID4-FID6 bottom | pass |
