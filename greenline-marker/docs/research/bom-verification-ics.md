# BOM verification — ICs, regulators, protection, crystal (GreenLine GL-1, rev A / EVT1)

Verification date: 2026-11-11. Web searches used: 45 of 45 allowed.

## How to read this report

Every field carries one of three marks.

- **confirmed** — seen today in a named source: a web-search extract (source number in brackets, list at the end), a file in the locally installed KiCad 7 library, or a public repository file read from GitHub.
- **corrected** — the value in the task or in `DESIGN_SPEC.md` was wrong or incomplete, and the replacement was seen in a named source.
- **not-confirmed** — no source seen today gives the value. Where a figure appears next to this mark it is labelled as general engineering knowledge or as my own arithmetic, and it must not be treated as verified.

Limits of the evidence:

- Vendor and distributor pages could not be opened. Web evidence is the text that the search tool returned, which is an extract or a summary of the page, not the page itself.
- Distributor stock and prices are snapshots of regional DigiKey or Mouser pages, or of aggregators (Findchips, flux.ai), with no date shown. No live US DigiKey page with 1 / 100 / 1000 price breaks was seen for any part. Each stock figure below names the page it came from.
- Maker headquarters are general knowledge; they were not searched.
- Files read from public repositories: ST `STM32_open_pin_data`, Zephyr `hal_stm32`, Analog Devices `msdk`, SparkFun `SparkFun-KiCad-Libraries` (all on raw.githubusercontent.com), and the official KiCad 8.0.0 and 9.0.0 `Sensor_Motion.kicad_sym` (gitlab.com, checked only for whether newer libraries contain the two ST sensors — they do not). No downloaded file was executed.
- One command that would have tested whether ST, OmniVision and EasyEDA hosts were reachable was refused by the sandbox before it ran. No vendor or distributor page was fetched.

## Summary

| # | Item | Final MPN | Status | What is still open |
|---|---|---|---|---|
| 1 | MCU | STM32U585RIT6 | partly-verified | Package height, USD price, Stop 2 current with RTC, crystal-less USB statement |
| 2 | Camera cube | OVM7692-RYAA | partly-verified | Ball map, ball pitch, row orientation, output state in power-down, lifecycle |
| 3 | IMU | LSM6DSV16XTR | partly-verified | Offset tempco, low-power current, US stock (0 at DigiKey US snapshot) |
| 4 | Inclinometer | IIS2ICLXTR | problem | Pin map for pins 3-7, 10, 11; no KiCad symbol or footprint; SPI mode |
| 5 | NOR flash | MX25R6435FZNIL0 | partly-verified | Package height; consistent US price |
| 6 | 3.0 V LDO | MCP1700T-3002E/TT | partly-verified | Dropout at 50 mA; live US stock and price |
| 7 | 2.8 V LDO | LP5907MFX-2.8/NOPB | partly-verified | Live US stock and price |
| 8 | Charger | MCP73831T-2ACI/OT | partly-verified | Absolute maximum VDD; USD price breaks |
| 9 | USB ESD | USBLC6-2SC6 | verified | — |
| 10 | Schottky | B0530WS-7-F (proposed) | verified | Body height |
| 11 | 32.768 kHz crystal | ABS07-32.768KHZ-T as specified; ABS07-120-32.768KHZ-T proposed instead | problem | 12.5 pF part needs the highest LSE drive setting; LSE table for the U585 itself not seen |

## Things that need a decision or a person

1. **OVM7692 ball map is still unknown.** Six searches found no public pin table, ball pitch or land pattern. The cube cannot be given a footprint from verified data. The two documents that contain it are the registered OmniVision datasheet and the Analog Devices MAX78000FTHR schematic PDF (the board carries OVM7692-RYAA as U1) [24]; neither could be opened here.
2. **IIS2ICLX pin map is still unknown for seven of sixteen pins,** and the fragments returned by search disagree with one another. There is no symbol or 5 x 5 mm ceramic LGA-16 footprint in KiCad 7, 8.0.0 or 9.0.0. A person must take the table from ST DS13005 and draw both.
3. **DCMI alternate functions are not all AF10.** PC9 (D3) and PA6 (PIXCLK) are AF4. PC11 offers DCMI_D4 on AF10 and DCMI_D2 on AF4; D4 needs AF10.
4. **PA6 is taken by DCMI_PIXCLK, so SPI1_MISO cannot be on PA6.** The flash shares SPI1 with the LCD and needs MISO; the other LQFP-64 options are PB4 (pad 56, AF5) or PA11, and PA11 is USB D-. PB4 is the only free choice.
5. **The LCD EXTCOMIN timer must be LPTIM1 or LPTIM3.** ST states LPTIM2 works only in Stop 0 and Stop 1 [7]. Pin choices are in section 1.
6. **OVM7692-RAAA is not a second source for -RYAA.** OmniVision lists it at 2815 x 3179 x 2600 um against 2950 x 3470 x 2760 um for -RYAA [16]. The prism stack and pockets are built on the -RYAA height.
7. **The 12.5 pF crystal is a poor match for the STM32 low-speed oscillator.** See section 11; the 6 pF ABS07-120-32.768KHZ-T has the same footprint.
8. **IIS2ICLX offset drift is published by ST as "below 0.075 mg/degC"** [30d, 30e], not 0.020 mg/degC. Over a 20 degC swing that bound is 1.5 mg, about 1.5 mrad, which is larger than the 0.5 mrad sensor figure in the design specification.
9. **Unverified risk, from memory only:** the STM32U5 datasheet gives a minimum VDDUSB of 3.0 V when USB is in use. The always-on rail is a nominal 3.0 V regulator fed from a cell that can be at 3.0-3.3 V on the cradle. Check the VDDUSB limits in DS13086 before freezing the rail voltage.
10. **Unverified risk:** MCU pins at 3.0 V drive camera inputs powered at 2.8 V (XVCLK, SIOC, PWDN). The 0.2 V excess is normally inside an input's rating, but the OVM7692 absolute maximum input voltage was not seen.

---

## 1. STM32U585RIT6 (MCU)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | STM32U585RIT6 (tray). The "Q" part STM32U585RIT6Q is the SMPS version and has a different pinout | confirmed — DigiKey listings [1-4]; KiCad has separate symbols `STM32U585RITx` and `STM32U585RITxQ` |
| Maker, HQ | STMicroelectronics, Geneva, Switzerland | general knowledge, not searched |
| Lifecycle | No status field seen. Stocked with price breaks on DigiKey regional sites | not-confirmed |
| Distributor | DigiKey, product page id 18085579, SKU 497-STM32U585RIT6-ND | confirmed [1-4] |
| Stock as seen | 1,497 (DigiKey LV page), 554 (UK page), 409 (AT page), 0 on one other regional page. No Mouser listing for this exact part was returned | confirmed as snapshots [1-3] |
| Price | AT: EUR 8.09 / 6.30 / 5.852 / 5.3596 at 1 / 10 / 25 / 100. UK: GBP 7.01 / 5.46 / 5.0724 / 4.6454. CA: CAD 15.14 / 11.779 / 10.9416 / 10.0207. No USD page and no 1000-piece price seen | confirmed for those pages [1, 2, 4]; USD not-confirmed |
| Manufacturer pack | Tray of 160 | confirmed [5] |
| Flash / RAM | 2048 kB / 786 kB | confirmed — ST open pin data [13], DigiKey "2MB" [1], KiCad symbol description |
| Supply range | 1.71-3.6 V | confirmed — ST open pin data [13], KiCad symbol description |
| Temperature (suffix 6) | -40 to +85 degC | confirmed [13] |
| Package | LQFP-64, 10 x 10 mm body, 0.5 mm pitch; KiCad footprint `Package_QFP:LQFP-64_10x10mm_P0.5mm` | confirmed [1, 13], KiCad symbol |
| Package height | Not seen. Standard LQFP is 1.4 mm body, 1.60 mm maximum seated height | not-confirmed (general knowledge) |
| Stop 2 current | Datasheet headline: 4.0 uA with 16 kB SRAM, 8.95 uA with full SRAM (DS13086 Rev 2). An earlier data brief gave 3.4 and 6.6 uA. A figure that explicitly includes the RTC was not found | partly confirmed [6]; "with RTC" not-confirmed |
| Crystal-less USB | Not returned by any search | not-confirmed (widely documented: HSI48 with clock recovery) |
| Errata | ES0499 exists for STM32U575/585 and should be read before relying on low-power behaviour | confirmed that it exists [11] |

### Pad numbers and alternate functions

Pad numbers come from the installed KiCad symbol `MCU_ST_STM32U5:STM32U585RITx`. All 64 pad-to-pin assignments were compared with ST's `STM32U585RITx.xml` [13] with no mismatch. Alternate-function numbers come from ST's `GPIO-STM32U5x_gpio_v1_0_Modes.xml` [13] and agree with the Zephyr pin-control file generated from it [12].

| Function | Pin | Pad | AF | Mark |
|---|---|---|---|---|
| DCMI_D0 | PC6 | 37 | AF10 | confirmed |
| DCMI_D1 | PC7 | 38 | AF10 | confirmed |
| DCMI_D2 | PC8 | 39 | AF10 | confirmed |
| DCMI_D3 | PC9 | 40 | **AF4** | confirmed; corrects the assumption of one AF for all |
| DCMI_D4 | PC11 | 52 | AF10 (the same pin offers DCMI_D2 on AF4) | confirmed |
| DCMI_D5 | PB6 | 58 | AF10 | confirmed |
| DCMI_D6 | PB8 | 61 | AF10 | confirmed |
| DCMI_D7 | PB9 | 62 | AF10 | confirmed |
| DCMI_PIXCLK | PA6 | 22 | **AF4** | confirmed |
| DCMI_HSYNC | PA4 | 20 | AF10 | confirmed |
| DCMI_VSYNC | PB7 | 59 | AF10 | confirmed |
| RCC_MCO | PA8 | 41 | AF0 | confirmed |
| OPAMP1_VINP | PA0 | 14 | analog | confirmed |
| OPAMP1_VINM | PA1 | 15 | analog | confirmed |
| OPAMP1_VOUT | PA3 | 17 | analog (also ADC1_IN8) | confirmed |
| USB_OTG_FS_DM | PA11 | 44 | AF10 | confirmed |
| USB_OTG_FS_DP | PA12 | 45 | AF10 | confirmed |
| VDDUSB | — | 48 | supply | confirmed (KiCad) |
| OSC32_IN / OSC32_OUT | PC14 / PC15 | 3 / 4 | — | confirmed |
| BOOT0 | PH3 | 60 | — | confirmed |
| SWDIO / SWCLK | PA13 / PA14 | 46 / 49 | — | confirmed |
| NRST | — | 7 | — | confirmed |

The pin plan in `DESIGN_SPEC.md` section 4 is therefore correct for pin names. The alternate-function line should read: AF10 for all DCMI pins except PC9 and PA6, which are AF4.

### Low-power timer output usable in Stop 2

| Finding | Mark and source |
|---|---|
| LPTIM2 is functional only in Stop 0 and Stop 1 | confirmed — ST knowledge article citing the reference manual [7] |
| LPTIM1 and LPTIM3 are autonomous in Stop 2 | confirmed — ST LPBAM wiki [8] |
| LPTIM4: sources disagree (wiki says passive in Stop 2, AN5645 lists it as functional) | not-confirmed [8, 9] |
| LPTIM1, 3, 4 need their autonomous clock-enable bit set to keep running in Stop 2 | confirmed [7] |
| That the PWM output pin keeps toggling in Stop 2 | not-confirmed — no result addressed it; check RM0456 chapter 58 [10] |

Output pins on LQFP-64 that do not collide with the camera, op-amp, USB or debug pins (KiCad symbol and [13]):

| Timer channel | Pin | Pad | AF |
|---|---|---|---|
| LPTIM1_CH1 | PB2 | 28 | AF1 |
| LPTIM1_CH1 | PC1 | 9 | AF1 |
| LPTIM3_CH1 | PB0 | 26 | AF4 |
| LPTIM3_CH1 | PB10 | 29 | AF2 |
| LPTIM3_CH1 | PC3 | 11 | AF2 |
| LPTIM3_CH2 | PB1 | 27 | AF4 |

Excluded because of conflicts: LPTIM1_CH2 on PA1 (op-amp input), LPTIM1_CH1 on PA14 (SWCLK) and PB3 (SWO), LPTIM3 on PC8 and PC9 (camera data), every LPTIM2 pin.

### Related pin facts found while checking (KiCad symbol)

- SPI1: SCK on PA5 (21) or PB3 (55); MOSI on PA7 (23) or PB5 (57); MISO on PA6 (22, taken by PIXCLK), PA11 (44, USB) or PB4 (56).
- SPI2: SCK on PB13 (34) or PB10 (29); MISO on PB14 (35) or PC2 (10); MOSI on PB15 (36), PC3 (11) or PC1 (9).
- Wake-up pins not taken by the camera, op-amp, USB or debug functions: PC13 (2, WKUP2), PA2 (16, WKUP4), PA5 (21, WKUP6), PA7 (23, WKUP8), PC5 (25, WKUP5), PB1 (27, WKUP4), PB2 (28, WKUP1), PB10 (29, WKUP8), PB15 (36, WKUP7), PB5 (57, WKUP6). Several of these are also the SPI and timer candidates listed above, so the IMU interrupt pin has to be chosen together with them. PC13 and PC5 carry none of those functions.

---

## 2. OVM7692-RYAA (camera cube)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | OVM7692-RYAA | confirmed [14, 16, 20] |
| -RAAA as alternative | Different size: 2815 x 3179 x 2600 um | corrected — not interchangeable mechanically [16, 18] |
| Maker, HQ | OmniVision, Santa Clara, California, USA | general knowledge, not searched |
| Lifecycle | No status field seen. OmniVision's product page is live and a product brief v1.9 sits under a 2026/04 path on ovt.com | not-confirmed (indirect evidence only) [15, 17] |
| Distributor | DigiKey 884-1027-1-ND, product page id 3516559 | confirmed [14, 20] |
| Stock as seen | 6,282 at DigiKey with minimum order 1 and a 20-week lead time (Findchips copy; the lead time sits oddly with the stock figure). LCSC C17590822 also lists it | confirmed as aggregator snapshot [14, 19] |
| Price | Findchips shows only a range for the DigiKey line, USD 6.25 to 44.95. LCSC shows USD 4.34 at 1000 and up | 1 / 100 / 1000 at DigiKey not-confirmed [14, 19] |
| Package size | 2950 x 3470 x 2760 um (brief v1.8; v1.7 prints the first two swapped) | confirmed [16, 18] |
| Ball count | 25, from third-party listings ("25-pin CSP", "CSP-25", "25-Pin BGA") | partly confirmed [19, 25]; not seen in an OmniVision document |
| Ball pitch | Not found | not-confirmed |
| Ball map | Not found. One third-party page lists DVP signal names without ball positions and was not used | not-confirmed [26] |
| AVDD range | 2.6-3.0 V | confirmed [18] |
| DOVDD range | 1.7-3.0 V | confirmed [18] |
| Core supply | Built-in 1.5 V regulator | confirmed [16, 17] |
| XVCLK range | 6-27 MHz (54 MHz also listed), from brief v1.6 / v1.7 | confirmed for older brief revisions [18]; not re-seen in v1.9 |
| SCCB address | 0x3C (7-bit), which is 0x78 write / 0x79 read | confirmed — Analog Devices driver `ov7692.c` [23] |
| Register 0x0C default | 0x16 | confirmed [23] |
| Register 0x0C bits 7, 6, 4 | Vertical flip, horizontal mirror, YU/YV swap | confirmed [23] |
| Register 0x0C bits 2 and 1 | In the OV7690 datasheet (sister sensor, same register name): bit 2 selects tri-state or driven for the data pins D[7:0], bit 1 the same for VSYNC, HREF and PCLK [21]. A second extract of that datasheet gives "0 = tri-state" for a data-pin and a clock-pin status bit, without showing the register address [22]. The OV7692 default 0x16 has both bits set, which fits "driven by default" [23] | partly confirmed — OV7690 document, not OV7692; polarity inferred |
| Register 0x0E bit 3 | Sleep mode enable | confirmed — `SLEEP_MODE_ENABLE 0x08` applied to REG0E [23] |
| PWDN pin | Active high with internal pull-down, on the OV7690 | partly confirmed — OV7690 document [22] |
| Outputs high-impedance in power-down | Not found | not-confirmed |
| Edge parallel to image rows | Not found | not-confirmed |
| Optics | f-number 3.0, diagonal field of view 64 deg (v1.9); focal length 1.15 mm for -RYAA / -RAAA (v1.6 / v1.7) | confirmed [17, 18] |
| Active power | About 120 mW at AVDD 2.8 V, DOVDD 1.8 V | confirmed [18] |
| MIPI | The brief states DVP parallel or MIPI serial output; the driver powers the MIPI block down through register 0xB5 in bank 1. Ball positions unknown | confirmed for existence [15, 23]; positions not-confirmed |

Notes:

- A 1.15 mm focal length over a 1.75 um pixel gives 657 pixels, which matches the figure in `DESIGN_SPEC.md`. The pixel size was not re-seen today.
- Because the register 0x0C polarity rests on the OV7690 document, firmware should set or clear bits 2 and 1 together and the result should be measured on the first board.
- Both cameras answer at the same fixed address, which is why the design gives each its own SCCB clock; the driver shows no address-select option [23].

---

## 3. LSM6DSV16XTR (IMU)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | LSM6DSV16XTR | confirmed [27] |
| Maker, HQ | STMicroelectronics, Geneva, Switzerland | general knowledge |
| Lifecycle | No status field seen; ST product page live | not-confirmed |
| Distributor | DigiKey 497-LSM6DSV16XTRCT-ND (cut tape); Mouser 511-LSM6DSV16XTR | confirmed [27] |
| Stock as seen | DigiKey US page: 0, with a per-30-day purchase limit. Mouser India page: 1,370 in stock, 5,000 on order | confirmed as snapshots [27] |
| Price | DigiKey US: USD 4.42 at 1 (cut tape); USD 2.78062 each at 5,000 (reel). 100 and 1000 not seen | confirmed for those two breaks [27] |
| Package | LGA-14L, 2.5 x 3.0 x 0.83 mm | confirmed — ST datasheet DS13510 extract [28] |
| Analog supply | 1.71-3.6 V | confirmed [28] |
| I/O supply range | Separate range exists; limits not seen | not-confirmed |
| Accelerometer offset tempco | Not reached in any extract | not-confirmed |
| Low-power or wake-up current | Not found. Only "0.65 mA, accelerometer plus gyroscope, high-performance mode" was seen | not-confirmed [28] |

### Pin map

| Pin | LSM6DSV16X (SparkFun KiCad symbol [29]; ST AN5763 extracts [28]) | KiCad 7 `Sensor_Motion:LSM6DSM` |
|---|---|---|
| 1 | SDO/SA0 | SDO/SA0 |
| 2 | SDx | SDX |
| 3 | SCx | SCX |
| 4 | INT1 | INT1 |
| 5 | VDDIO | VDDIO |
| 6 | GND | GND |
| 7 | GND | GND |
| 8 | VDD | VDD |
| 9 | INT2 | INT2 |
| 10 | OCS_Aux | OCS_Aux |
| 11 | SDO_Aux | SDO_Aux |
| 12 | CS | CS |
| 13 | SCL | SCL |
| 14 | SDA | SDA |

Mark: **confirmed.** The SparkFun symbol is the one used on their shipping LSM6DSV16X breakout. ST's AN5763, as returned by search, independently gives pin 1 SDO/SA0, pin 4 INT1, pin 9 INT2, pin 10 OCS_Aux, pin 11 SDO_Aux.

Result: the 14 pins are functionally the same as the KiCad `LSM6DSM` symbol for 4-wire SPI with INT1 and INT2 (CS 12, clock 13, data in 14, data out 1). The installed symbol `Sensor_Motion:LSM6DSM` and footprint `Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y` can be used. In that footprint pads 1-4 are on the left 2.5 mm side, 5-7 along the bottom, 8-11 on the right, 12-14 along the top.

Wiring of unused pins per the AN5763 extract [28]: pins 10 and 11 connect to VDDIO or are left open in modes 1 and 2. The treatment of pins 2 and 3, and any power-on restriction on INT1, were not seen and should be read from DS13510.

---

## 4. IIS2ICLXTR (precision inclinometer, EVT option)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | IIS2ICLXTR | confirmed [30a] |
| Maker, HQ | STMicroelectronics, Geneva, Switzerland | general knowledge |
| Lifecycle | Active; manufacturer lead time 24 weeks | confirmed — DigiKey listing [30a] |
| Distributor | DigiKey product pages 11590957 and 12703503 (DigiKey SKU text not seen); Mouser 511-IIS2ICLXTR (printed "511-IIS2ICLX TR" in the extract) | confirmed [30a, 30b, 30c] |
| Stock as seen | DigiKey Singapore page: 8,993. Mouser India page: 3,775 | confirmed as snapshots [30b, 30c] |
| Price | DigiKey Belgium page, in USD: about 28.28 at 1 (cut tape), about 20.05 each at 3,000 (reel). 100 and 1000 not seen | confirmed for those breaks [30a] |
| Package | Ceramic cavity LGA-16, 5 x 5 x 1.7 mm | confirmed — datasheet title line and RS listing [30d, 30f] |
| Supply | 1.71-3.6 V | confirmed [30a, 30d] |
| Interface | I2C or SPI | confirmed [30d] |
| SPI mode (0 or 3) | Not found | not-confirmed |
| Noise density | 15 ug/sqrt(Hz) | confirmed — ST product page [30d] |
| Offset change with temperature | Below 0.075 mg/degC | corrected — 0.020 mg/degC was not found anywhere [30d, 30e] |
| Current | 0.42 mA | confirmed — ST presentation [30e] |
| Temperature range | -40 to +105 degC (an RS listing says 85 degC; ST is the authority) | confirmed [30d] |

### Pin map — not confirmed

Five searches were spent on this. What came back:

| Pin | Name | Source and weight |
|---|---|---|
| 1 | VDD_IO | ST AN5509 Table 1, returned consistently — confirmed [30g] |
| 2 | CS | ST AN5509 Table 1, returned consistently — confirmed [30g] |
| 8 | VDD | ST AN5509 Table 1, one extract — probable [30g] |
| 9 | VDD | ST AN5509 Table 1, one extract — probable [30g] |
| 12 | SCx (master I2C clock in mode 2; tie to GND or VDD_IO otherwise) | ST DS13005 extract — confirmed [30d] |
| 13 | GND | ST DS13005 extract — confirmed [30d] |
| 14, 15, 16 | NC (connect to GND or leave open) | ST DS13005 extract — confirmed [30d] |
| 3-7, 10, 11 | unknown | not-confirmed |

Fragments that could not be reconciled and were discarded: one extract put GND on pin 3 and the INT2 function on pin 4; another put INT1, SDx and VDD "near" pins 6, 7, 8; a parts-broker page gave a list that puts CS on pin 5, contradicting ST. None of these should be used.

There is no IIS2ICLX symbol in the installed KiCad 7 library or in the official 8.0.0 and 9.0.0 libraries, and the installed footprint library has LGA-16 only at 3 x 3 mm and 4 x 4 mm. Symbol and footprint must be drawn from DS13005. This line stays PROVISIONAL.

Other notes: the part is 1.7 mm tall, so it cannot sit under the battery; and at about USD 28 it costs more than the microcontroller.

---

## 5. SPI NOR flash

Recommended: **Macronix MX25R6435FZNIL0**, 64 Mbit, 8-WSON 6 x 5 mm.

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | MX25R6435FZNIL0 | confirmed [31a] |
| Maker, HQ | Macronix International, Hsinchu, Taiwan | general knowledge |
| Lifecycle | No status field seen | not-confirmed |
| Electrical | 64 Mbit, SPI with quad I/O, 80 MHz, 1.65-3.6 V, -40 to +85 degC | confirmed [31a] |
| Package | 8-WSON, 6 x 5 mm | confirmed [31a] |
| Height | Not found | not-confirmed |
| Distributor | DigiKey product page 6558605 | confirmed [31a] |
| Stock as seen | 62,321 (UK page), 51,525 (DE page), 0 (IE page); a US page extract says backorders are not being accepted because of constrained supply | confirmed as snapshots, and they conflict [31a] |
| Price | Two different US-page extracts: USD 2.68 at 1 falling to 2.13 at 1,140 (tray); and USD 1.53 at 1 falling to 1.22 at 1,140 | conflicting; treat as not-confirmed [31a] |
| KiCad footprint | `Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4mm` — the footprint KiCad's own Macronix symbol `Memory_Flash:MX25R3235FZNxx0` uses for the same "ZN" package | confirmed (local library) |
| Pin order | 1 CS#, 2 SO/SIO1, 3 WP#/SIO2, 4 GND, 5 SI/SIO0, 6 SCLK, 7 RESET# or HOLD#/SIO3, 8 VCC, 9 exposed pad to GND | confirmed — KiCad Macronix and Winbond symbols agree |

Smaller option, not yet verified as a footprint match: **MX25R6435FZAIL0**, 8-USON 4 x 4 mm (DigiKey product page 7402343, also described there as "8-UDFN Exposed Pad") [31b].

- Stock as seen: 0 on one DigiKey page (USD 1.49 at 1), 1,411 and 6,953 on two other regional pages; Future Electronics shows a factory lead time over 52 weeks; LCSC shows 78 pieces [31b].
- The library has 8-pin 4 x 4 mm footprints at 0.8 mm pitch (`Package_SON:WSON-8-1EP_4x4mm_P0.8mm_EP2.2x3mm`, `..._EP2.6x3mm`, `..._EP1.98x3mm`, `Package_DFN_QFN:DFN-8-1EP_4x4mm_P0.8mm_EP2.3x3.24mm`), but the Macronix pitch and exposed-pad size were not found, so none can be named as the match.
- The library has no 4 x 3 mm or 2 x 3 mm 8-pin footprint at the pitches flash makers use.

Answer to the question as asked: the smallest leadless package for which a library footprint is confirmed is the 6 x 5 mm WSON. W25Q64JV was not searched (budget); for its 6 x 5 mm WSON the library footprint is `Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm`, drawn from Winbond's own datasheet.

---

## 6. MCP1700T-3002E/TT (3.0 V always-on regulator)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | MCP1700T-3002E/TT | confirmed [32a] |
| Maker, HQ | Microchip Technology, Chandler, Arizona, USA | general knowledge |
| Lifecycle | No status field seen | not-confirmed |
| Package | SOT-23 (3-lead) | confirmed [32a] |
| Pin order | 1 GND, 2 VOUT, 3 VIN | confirmed — KiCad symbol `Regulator_Linear:MCP1700x-300xxTT`; a datasheet extract puts VIN on pin 3 [32c] |
| KiCad symbol `Regulator_Linear:MCP1700-3002E_SOT23` | Not present in the installed library. The symbol is `Regulator_Linear:MCP1700x-300xxTT`, footprint `Package_TO_SOT_SMD:SOT-23` | corrected (local library) |
| Quiescent current | 1.6 uA typical (DigiKey's parameter field shows 4 uA) | confirmed [32c] |
| Maximum input | 6 V; operating range 2.3-6.0 V from a distributor listing | confirmed [32a, 32d] |
| Dropout | 178 mV typical at 250 mA (VOUT 2.8 V); one source lists 350 mV maximum. No 50 mA figure seen. Linear scaling would give about 36 mV — my arithmetic, not a datasheet value | 250 mA confirmed [32c]; 50 mA not-confirmed |
| Stable with 1 uF ceramic | Typical application circuits use 1 uF ceramic on input and output; the exact stability statement was not returned | partly confirmed [32c] |
| Distributor | DigiKey product pages 651114 and 1979825; cut-tape SKU MCP1700T-3002E/TTCT-ND | confirmed [32a] |
| Stock as seen | Aggregator: 38,968 on the DigiKey cut-tape line; another aggregator 70,266. DigiKey Austria page: out of stock. DigiKey Canada page: 15-week lead time | conflicting snapshots [32a, 32b] |
| Price | About USD 0.51 each (aggregator, DigiKey cut-tape line). 100 and 1000 not seen | partly confirmed [32b] |

---

## 7. LP5907MFX-2.8/NOPB (2.8 V camera regulator)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | LP5907MFX-2.8/NOPB | confirmed [33a] |
| Maker, HQ | Texas Instruments, Dallas, Texas, USA | general knowledge |
| Lifecycle | No status field seen; TI datasheet revised July 2025 (SNVS798Q) | not-confirmed explicitly [33b] |
| Package | SOT-23-5 | confirmed [33a] |
| Pin order | 1 IN, 2 GND, 3 EN, 4 N/C, 5 OUT | confirmed — KiCad symbol `Regulator_Linear:LP5907MFX-2.8`; flux.ai part page [33c] |
| Quiescent current | 12 uA enabled; below 1 uA disabled (DigiKey's parameter field shows 25 uA) | confirmed [33b] |
| Output noise | Below 6.5 uVrms, no bypass capacitor needed | confirmed [33b] |
| Capacitors | Stable with 1 uF ceramic input and output | confirmed [33b] |
| Other | Input 2.2-5.5 V; dropout 120 mV typical; 250 mA | confirmed [33b] |
| Distributor | DigiKey product pages 3906436 and 5143092 | confirmed [33a] |
| Stock as seen | flux.ai copy of DigiKey: 18K, undated. One DigiKey Mexico page: out of stock. Another page: 6-week lead time | conflicting snapshots [33a, 33c] |
| Price | USD 0.65 (flux.ai copy, undated). Breaks not seen | partly confirmed [33c] |

---

## 8. MCP73831T-2ACI/OT (charger)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | MCP73831T-2ACI/OT | confirmed [34c] |
| Maker, HQ | Microchip Technology, Chandler, Arizona, USA | general knowledge |
| Lifecycle | No status field seen | not-confirmed |
| Package, regulation voltage | SOT-23-5, 4.20 V | confirmed — KiCad symbol description; distributor listings [34d] |
| Pin order | 1 STAT, 2 VSS, 3 VBAT, 4 VDD, 5 PROG | confirmed — KiCad symbol `Battery_Management:MCP73831-2-OT`; datasheet extract [34a] |
| Charge current formula | I = 1000 V / R_PROG. The formula text was garbled in the extract; the datasheet's own points (100 mA at 10 kohm, 505 mA at 2 kohm) fit it | confirmed [34a] |
| 49.9 kohm | 20.04 mA (arithmetic from the formula) | confirmed by calculation |
| Programmable range | 15-500 mA; R_PROG 2 kohm to 67 kohm (67 kohm gives 14.9 mA) | confirmed [34a, 34b] |
| PROG floating | Device disabled and charge cycle ended; a logic high on PROG does the same; supply current about 25 uA when disabled | confirmed [34a] |
| Operating VDD | 3.75-6 V | confirmed [34d] |
| Absolute maximum VDD | Not found | not-confirmed |
| Distributor | DigiKey product page 964301; cut-tape SKU MCP73831T-2ACI/OTCT-ND | confirmed [34c] |
| Stock as seen | DigiKey Canada page: 50,036. A UK page for listing 1979802: out of stock | conflicting snapshots [34c] |
| Price | DigiKey Latvia page: EUR 0.66 at 1; 4-week lead time. USD breaks not seen | partly confirmed [34c] |

The scheme in the design specification (PROG resistor returned to ground through a transistor or an open-drain pin) is consistent with the confirmed PROG behaviour.

---

## 9. USBLC6-2SC6 (USB ESD protection)

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | USBLC6-2SC6 | confirmed [35] |
| Maker, HQ | STMicroelectronics, Geneva, Switzerland | general knowledge |
| Lifecycle | No status field seen; heavily stocked | not-confirmed explicitly |
| Package | SOT-23-6 | confirmed [35] |
| Pin order | 1 I/O1, 2 GND, 3 I/O2, 4 I/O2, 5 VBUS, 6 I/O1 | confirmed — KiCad symbol `Power_Protection:USBLC6-2SC6` (the search returned no pin table) |
| Ratings | 5.25 V working, 17 V clamp, 5 A (8/20 us) | confirmed [35] |
| Distributor | DigiKey 497-5235-1-ND (cut tape); product pages 1040559 and 1121688 | confirmed [35] |
| Stock as seen | 156,665 (Findchips copy of DigiKey); 67,477 in a second Findchips view; 162,291 on the DigiKey UK page; 25-week lead time | confirmed as snapshots [35] |
| Price | USD 0.36 at 1; USD 0.114 at 1,000 (Findchips copy of DigiKey). 100 not seen | confirmed for those breaks [35] |

---

## 10. Series Schottky diode, pad to charger (proposal)

Proposed: **Diodes Incorporated B0530WS-7-F**, 30 V, 0.5 A, SOD-323.

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | B0530WS-7-F | confirmed [36a] |
| Maker, HQ | Diodes Incorporated, Plano, Texas, USA | general knowledge |
| Lifecycle | Active | confirmed — DigiKey Japan page [36a] |
| Ratings | 30 V, 500 mA | confirmed [36a, 36b] |
| Forward voltage | 0.45 V maximum at 0.5 A; 0.40 V typical per the maker's datasheet extract | confirmed [36a, 36b] |
| Reverse leakage | 500 uA at 30 V | confirmed — DigiKey UK page [36a] |
| Capacitance | 58 pF at 0 V | confirmed [36a] |
| Package | SOD-323; KiCad footprint `Diode_SMD:D_SOD-323` | confirmed [36a], local library |
| Body height | Not found | not-confirmed |
| Distributor | DigiKey B0530WS-FDICT-ND (cut tape); product pages 816548 and 816523 | confirmed [36a] |
| Stock as seen | About 108,418 with a 40-week lead time (Findchips copy); a DigiKey Austria page shows out of stock | conflicting snapshots [36a, 36c] |
| Price | USD 0.30 at 1; USD 0.07417 at 1,000 (US-dollar DigiKey page). 100 not seen | confirmed for those breaks [36a] |

Alternative considered: onsemi NSR0530HT1G (SOD-323, 30 V, 0.5 A). Distributor listings give its forward voltage as 0.52 V to 0.62 V maximum at 0.5 A, which is higher [36d], so it is the weaker choice. No Vishay part appeared in the results.

At the 20 mA charge current the drop will be well below the 0.5 A figure; the value at 20 mA was not seen.

---

## 11. 32.768 kHz crystal

### As specified: Abracon ABS07-32.768KHZ-T

| Field | Value | Mark and source |
|---|---|---|
| Orderable MPN | ABS07-32.768KHZ-T | confirmed [37a] |
| Maker, HQ | Abracon LLC, Spicewood, Texas, USA | general knowledge |
| Lifecycle | No status field seen | not-confirmed |
| Frequency, tolerance | 32.768 kHz, +/-20 ppm | confirmed [37a] |
| Load capacitance | 12.5 pF | confirmed [37a] |
| ESR | 70 kohm | confirmed [37a] |
| Size | 3.2 x 1.5 mm, 0.9 mm high (height from a Newark listing quoted in the search summary; its address was not shown) | size confirmed [37a]; height partly confirmed |
| Distributor | DigiKey 535-9542-1-ND (cut tape), -2-ND (reel), -6-ND (Digi-Reel); product page 1236858 | confirmed [37a] |
| Stock as seen | Unclear. One DigiKey page showed 771,689 but the extract did not tie it to this part; an Austria page showed out of stock; lead time 14 weeks | not-confirmed |
| Price | USD 0.694 at 1, 0.512 at 250, 0.465 at 1,000 (Findchips, partly from partner stock) | partly confirmed [37b] |
| KiCad footprint | `Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm` (drawn from the Epson FC-135 land pattern; the match to Abracon's recommended land was not checked) | local library |

### Concern and proposed change

The oscillator must supply a transconductance above the crystal's critical value, gm_crit = 4 x ESR x (2 pi f)^2 x (C0 + CL)^2.

| Crystal | CL | ESR | gm_crit with C0 = 1.0 to 1.5 pF (my arithmetic; C0 assumed) |
|---|---|---|---|
| ABS07-32.768KHZ-T | 12.5 pF | 70 kohm | 2.16 to 2.33 uA/V |
| ABS07-120-32.768KHZ-T | 6 pF | 55 kohm | 0.46 to 0.52 uA/V |

STM32 low-speed oscillator limits seen today, in the STM32L412 and STM32WB55 datasheets: maximum critical crystal gm of 0.5, 0.75, 1.7 and 2.7 uA/V for the four drive settings [38]. The same table for the STM32U575/585 was **not** seen, so applying it to this MCU is an assumption to be checked in DS13086.

If the table is the same, the 12.5 pF crystal runs only at the highest drive setting, with little margin and the highest oscillator current. The 6 pF part runs at the second-lowest setting.

Proposed replacement: **Abracon ABS07-120-32.768KHZ-T**.

| Field | Value | Mark and source |
|---|---|---|
| Specification | 32.768 kHz, +/-20 ppm, 6 pF, 55 kohm, 3.2 x 1.5 mm | confirmed [37c] |
| Distributor | DigiKey product page 3724043 | confirmed [37c] |
| Stock as seen | 110,303 (UK page), 90,489 (Canada page); one page showed out of stock; lead time 14 weeks | confirmed as snapshots [37c] |
| Price | USD 0.68 at 1, about USD 0.45 at 1,000 (US-dollar page) | confirmed for those breaks [37c] |

Load capacitors must be recalculated for 6 pF if the change is accepted.

---

## Sources

Web pages are listed as returned by the search tool. Local and repository files are listed last.

1. https://www.digikey.co.uk/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579
2. https://www.digikey.at/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579
3. https://www.digikey.lv/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579
4. https://www.digikey.ca/en/products/detail/stmicroelectronics/STM32U585RIT6/18085579
5. https://www.tme.eu/rs/en/details/stm32u585rit6/st-microcontrollers/stmicroelectronics/
6. STM32U585 datasheet copies: https://www.alldatasheet.net/datasheet-pdf/pdf/1587510/STMICROELECTRONICS/STM32U585XX.html ; https://www.mouser.com/pdfDocs/stm32u585ai.pdf ; https://www.mouser.com/datasheet/2/389/stm32u585qi-2529023.pdf
7. https://community.st.com/t5/stm32-mcus/troubleshooting-waking-up-from-stop-mode-issues-with-lptim-in/ta-p/745343
8. https://wiki.st.com/stm32mcu/wiki/Getting_started_with_LPBAM
9. https://www.st.com/resource/en/application_note/an5645-stm32u5-series-power-optimization-using-lpbam-stmicroelectronics.pdf
10. https://stm32.dirba.io/rm0456-stm32u5/58-low-power-timer-lptim/
11. https://www.st.com.cn/resource/en/errata_sheet/es0499-stm32u575xx-and-stm32u585xx-device-errata-stmicroelectronics.pdf
12. https://raw.githubusercontent.com/zephyrproject-rtos/hal_stm32/main/dts/st/u5/stm32u585ritx-pinctrl.dtsi (read directly)
13. https://raw.githubusercontent.com/STMicroelectronics/STM32_open_pin_data/master/mcu/STM32U585RITx.xml and https://raw.githubusercontent.com/STMicroelectronics/STM32_open_pin_data/master/mcu/IP/GPIO-STM32U5x_gpio_v1_0_Modes.xml (read directly)
14. https://www.findchips.com/detail/ovm7692-ryaa/Omnivision-Technologies-Inc
15. https://www.ovt.com/products/ovm7692/
16. https://ovt.com/wp-content/uploads/2024/09/OVM7692-PB-v1.8-WEB.pdf
17. https://www.ovt.com/wp-content/uploads/2026/04/OVM7692-PB-v1.9-WEB.pdf
18. Older OVM7692 product-brief copies: https://docs.rs-online.com/8fe1/0900766b80e99ac2.pdf ; https://cdn.components.ru/media/PDF/6553280.pdf ; https://datasheet.chipsmall.com/OVM7692-RYAA/441360.pdf ; https://dtsheet.com/doc/1709523/download-document
19. https://www.lcsc.com/product-detail/C17590822.html
20. https://www.digikey.com/en/products/detail/omnivision-technologies-inc/OVM7692-RYAA/3516559
21. https://datasheet.octopart.com/OV7690-Omnivision-Technologies-datasheet-141422473.pdf
22. http://aitendo3.sakura.ne.jp/aitendo_data/product_img/camera/OV7690/ov7690_full.pdf
23. https://raw.githubusercontent.com/analogdevicesinc/msdk/main/Libraries/MiscDrivers/Camera/ov7692.c and .../ov7692_regs.h (read directly)
24. https://www.analog.com/media/en/technical-documentation/data-sheets/MAX78000FTHR.pdf (identified, not opened)
25. https://www.snapeda.com/parts/OVM7692-RCAA/Omnivision%20Technologies/view-part/
26. https://www.xecor.com/product/ovm7692-raaa (not relied on)
27. https://www.digikey.com/en/products/detail/stmicroelectronics/LSM6DSV16XTR/16841908 ; https://www.digikey.ca/en/products/detail/stmicroelectronics/LSM6DSV16XTR/16841485 ; https://www.mouser.in/c/?marcom=106149961
28. LSM6DSV16X documents: https://www.st.com/en/mems-and-sensors/lsm6dsv16x.html ; https://cdn.sparkfun.com/assets/4/1/8/e/2/lsm6dsv16x.pdf ; https://static6.arrow.com/aropdfconversion/3cbea110d75a212f2a1cc9e883d903d45cbc7b7a/lsm6dsv16x.pdf ; https://cdn.sparkfun.com/assets/0/a/c/c/9/an5763-lsm6dsv16x-6axis-imu-with-embedded-sensor-fusion-ai-qvar-for-highend-applications-stmicroelectronics.pdf ; https://wiki.adom.inc/p/pg_azmgtmzdy7 ; https://blog.st.com/?p=25597
29. https://raw.githubusercontent.com/sparkfun/SparkFun-KiCad-Libraries/main/symbols/SparkFun-Sensor.kicad_sym (read directly)
30. IIS2ICLX: (a) https://www.digikey.be/en/products/detail/stmicroelectronics/IIS2ICLXTR/12703503 ; (b) https://www.digikey.sg/en/products/detail/stmicroelectronics/IIS2ICLXTR/11590957 ; (c) https://www.mouser.in/en/c/?marcom=156319684 ; (d) https://www.st.com/en/mems-and-sensors/iis2iclx.html , https://www.st.com/resource/en/datasheet/iis2iclx.pdf , https://www.farnell.com/datasheets/3108739.pdf , https://cdn.sparkfun.com/assets/0/7/f/7/0/IIS2ICLX_Datasheet.pdf ; (e) https://www.st.com/content/dam/sensor-and-test/presentations/stmicroelectronics-sensortest2020-industrial-sensors-overview.pdf ; (f) https://uk.rs-online.com/web/p/motion-sensor-ics/2049946 ; (g) https://www.st.com/resource/en/application_note/an5509-iis2iclx-highaccuracy-highresolution-lowpower-2axis-digital-inclinometer-stmicroelectronics.pdf ; discarded: https://www.lovechip.com/product/iis2iclxtr
31. Flash: (a) https://www.digikey.com/en/products/detail/macronix/MX25R6435FZNIL0/6558605 and the .co.uk, .de, .ie pages of the same id ; (b) https://www.digikey.ie/en/products/detail/macronix/MX25R6435FZAIL0/7402343 , https://azcus.digikey.com/en/products/detail/macronix/MX25R6435FZAIL0/7402343 , https://www.futureelectronics.com/p/5065464 , https://fat.lcsc.com/product-image/C2802847.html , https://www.cytechsystems.com/de/product/mx25r6435fzail0
32. MCP1700: (a) https://www.digikey.ca/en/products/detail/microchip-technology/MCP1700T-3002E-TT/651114 , https://www.digikey.be/en/products/detail/microchip-technology/MCP1700T-3002E-TT/1979825 , https://punchouttest.digikey.at/en/products/detail/microchip-technology/MCP1700T-3002E-TT/651114 ; (b) https://findchips.com/detail/mcp1700t-3002e%2Ftt/Microchip-Technology-Inc , https://www.embeddedrelated.com/parts/p/MCP1700T-3002E/TT ; (c) https://www.farnell.com/datasheets/1784514.pdf , https://www.radiolocman.com/datasheet/pdf.html?di=128895 , https://www.alldatasheet.net/datasheet-pdf/pdf/115220/MICROCHIP/MCP1700.html ; (d) https://uk.rs-online.com/web/p/voltage-regulators/6989063P
33. LP5907: (a) https://www.digikey.cn/en/products/detail/texas-instruments/LP5907MFX-2-8-NOPB/3906436 , https://www.digikey.com.br/en/products/detail/texas-instruments/LP5907MFX-2-8-NOPB/5143092 ; (b) https://www.ti.com/product/LP5907/datasheet , https://www.ti.com/lit/gpn/LP5907 , https://www.zeuthen.desy.de/~sulanke/Projects/ICECUBE/mDOM/mainboard/datasheets/vreg_ultra-low-noise_250mA_SOT23_LP5907.pdf ; (c) https://www.flux.ai/vasy_skral/lp5907mfx-2p8nopb.md
34. MCP73831: (a) https://www.farnell.com/datasheets/1784520.pdf , https://cdn.sparkfun.com/assets/2/c/c/5/a/MCP73831.pdf , https://www.radiolocman.com/datasheet/pdf.html?di=128841 ; (b) https://www.lcsc.com/blog/mcp73831-battery-charger-ic-guide/ ; (c) https://www.digikey.ca/en/products/detail/microchip-technology/MCP73831T-2ACI-OT/964301 , https://www.digikey.lv/en/products/detail/microchip-technology/MCP73831T-2ACI-OT/964301 , https://www.digikey.co.uk/en/products/detail/microchip-technology/MCP73831T-2ACI-OT/1979802 ; (d) https://www.futureelectronics.com/p/1359256 , https://nz.rs-online.com/web/p/battery-management/7386360
35. USBLC6-2SC6: https://www.findchips.com/detail/USBLC6-2SC6/STMicroelectronics ; https://www.findchips.com/search/STMicroelectronics%20USBLC6-2SC6 ; https://www.digikey.co.uk/en/products/detail/stmicroelectronics/USBLC6-2SC6/1121688 ; https://www.digikey.co.uk/en/products/detail/stmicroelectronics/USBLC6-2SC6/1040559
36. Schottky: (a) https://azcus.digikey.com/en/products/detail/diodes-incorporated/B0530WS-7-F/816548 , https://www.digikey.co.uk/en/products/detail/diodes-incorporated/B0530WS-7-F/816523 , https://www.digikey.jp/en/products/detail/diodes-incorporated/B0530WS-7-F/816548 , https://www.digikey.at/en/products/detail/diodes-incorporated/B0530WS-7-F/816548 ; (b) https://www.digikey.dk/en/htmldatasheets/production/61310/0/0/1/b0530ws.html , https://www.radiolocman.com/datasheet/data.html?di=99112 ; (c) https://www.findchips.com/search/b0530ws ; (d) https://octopart.com/part/onsemi/NSR0530HT1G , https://www.lcsc.com/product-detail/C556393.html , https://au.element14.com/on-semiconductor/nsr0530ht1g/schottky-rectifier-0-5a-30v-sod/dp/2508350
37. Crystal: (a) https://www.digikey.com/en/products/detail/abracon-llc/ABS07-32-768KHZ-T/1236858 , https://www.digikey.com.br/en/products/detail/abracon-llc/ABS07-32-768KHZ-T/1236858 ; (b) https://origin-www.findchips.com/detail/abs07-32.768khz-t/Abracon-Corporation ; (c) https://www.digikey.co.uk/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043 , https://www.digikey.com.mx/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043 , https://www.digikey.ca/en/products/detail/abracon-llc/ABS07-120-32-768KHZ-T/3724043
38. STM32 low-speed oscillator limits (other families): https://www.alldatasheet.com/html-pdf/1278473/STMICROELECTRONICS/STM32L412R8U3PXXX/267221/117/STM32L412R8U3PXXX.html ; https://community.st.com/t5/stm32-mcus-wireless/clarification-on-lse-crystal-drive-level-and-gmcritmax-for/td-p/826680 ; https://community.st.com/t5/stm32-mcus-products/stm32l475-lse-crystal-oscillator-doesn-t-tune-correctly-gmcrit/td-p/311651

Local files used (installed KiCad 7 library):

- `/usr/share/kicad/symbols/MCU_ST_STM32U5.kicad_sym` — `STM32U585RITx`
- `/usr/share/kicad/symbols/Sensor_Motion.kicad_sym` — `LSM6DS3`, `LSM6DSL`, `LSM6DSM`
- `/usr/share/kicad/symbols/Regulator_Linear.kicad_sym` — `MCP1700x-300xxTT`, `LP5907MFX-2.8`
- `/usr/share/kicad/symbols/Battery_Management.kicad_sym` — `MCP73831-2-OT`
- `/usr/share/kicad/symbols/Power_Protection.kicad_sym` — `USBLC6-2SC6`
- `/usr/share/kicad/symbols/Memory_Flash.kicad_sym` — `MX25R3235FZNxx0`, `W25Q32JVZP`
- `/usr/share/kicad/footprints/Package_SON.pretty`, `Package_DFN_QFN.pretty`, `Package_LGA.pretty`, `Package_QFP.pretty`, `Crystal.pretty`, `Diode_SMD.pretty`

Also read, to check whether newer official libraries contain the two ST sensors (they do not): `https://gitlab.com/kicad/libraries/kicad-symbols/-/raw/8.0.0/Sensor_Motion.kicad_sym` and the same path at tag `9.0.0`.
