# GreenLine research: processor and Bluetooth LE core that can capture micro-camera frames

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web.

- Web search: all four queries attempted were refused ("web search budget is used up", a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.sparkfun.com`, `learn.sparkfun.com`, `www.silabs.com` and `www.st.com` all failed to resolve. The session's network policy allows only package registries, MCP servers and a handful of unrelated hosts. No further hosts were tried, as instructed by the tool.
- GitHub: the session's GitHub access is limited to this repository, so vendor source code (the HM01B0 driver, ST pin-data files) could not be read either.

Consequences:

- **No part number, dimension, price, stock level, lifecycle status or FCC ID in this document was confirmed against a live source in this pass.** Every such item is marked UNVERIFIED. The values are carried forward from the first report, which took most of them from search-result extracts and regional distributor pages and could not open sparkfun.com itself.
- What was checked here: the first report's arithmetic (recomputed with a local script), its internal consistency, and its engineering logic. Several corrections came out of that; they are listed in sections 5 and 6.
- Where the reviewer's own recollection of a datasheet or driver (model training data, up to about mid-2026) agrees or disagrees with the report, that is stated as "reviewer recollection". Recollection is not a source and does not change an UNVERIFIED mark.
- The change in recommendation in section 2 is a re-ordering based on risk and on the recomputed numbers. It is not based on new facts.

Before design freeze, a person or a follow-up session with network access must open the manufacturer datasheets and the live US distributor pages for the three parts in section 2. Hosts that need to be allowed: `www.sparkfun.com`, `learn.sparkfun.com`, `cdn.sparkfun.com`, `community.sparkfun.com`, `www.st.com`, `www.silabs.com`, `www.digikey.com`, `www.mouser.com`, `www.arrow.com`, `www.newark.com`, `apps.fcc.gov` (or `fccid.io`), `www.u-blox.com`, `content.u-blox.com`, `www.ezurio.com`, `www.nordicsemi.com`, `docs.nordicsemi.com`, `alifsemi.com`, `ambiq.com`, `www.espressif.com`, `github.com`, `raw.githubusercontent.com`.

## 1. Summary

The first report recommended the SparkFun Artemis module (WRL-15484, Ambiq Apollo3 Blue) as a single certified compute-plus-radio core, with a two-chip fallback of an STM32U585 camera host and a Silicon Labs BGM220S certified BLE module. It attached two conditions to the Artemis choice: the cameras stay at 320 x 320 8-bit parallel (Himax HM01B0 class), and SparkFun confirms production supply.

Findings of this review:

1. The report's arithmetic is correct: the RAM budget, the 45-pin GPIO count and its variants, the unit conversion for the u-blox module, and the price sum.
2. Neither condition on the Artemis choice could be confirmed, and both look weak.
   - Supply: the first report's own evidence shows zero stock at DigiKey and on Octopart, several overseas resellers listing the part as retired, and only an undated crawl of the SparkFun page saying "In stock". Under the project's definition of US-sourceable (purchasable in production quantities from a US distributor or vendor today), that evidence does not establish the Artemis module as sourceable. It does report thousands of units of both fallback parts at DigiKey.
   - Resolution: a recomputation of stereo range resolution (section 4, finding 3) shows that a 320-pixel-wide image with a 30-36 mm baseline gives about 0.5-1.0 pixel of disparity at 10 m. With 0.1 pixel matching error the range error at 10 m is about 1.0-2.1 m (10-21%). The camera work is therefore likely to ask for VGA or higher, which the report itself names as a trigger for switching to the fallback.
3. The Artemis camera path is a software loop that polls GPIO pins, with field problems reported. A hardware camera port with DMA (STM32 DCMI) is more robust and works with any 8-bit parallel sensor at its normal pixel clock, so it keeps the camera choice open.
4. The statement that Artemis is "the only certified module with a public HM01B0 capture path" is probably too strong (reviewer recollection of other public parallel-camera capture paths; UNVERIFIED). The first report also did not evaluate ESP32-S3 modules, which by reviewer recollection are pre-certified and have a hardware 8-bit camera port.
5. The summary of the first report calls the Artemis price and stock "verified". They were not: the report states that sparkfun.com could not be opened.

Result: the recommendation is re-ordered. The two-chip route becomes the design baseline. The Artemis module is kept as a prototype vehicle and conditional alternate. All live facts for both routes remain UNVERIFIED.

## 2. Final recommendation after review (live facts UNVERIFIED)

### Design baseline: two chips

- **Camera host and application processor: STMicroelectronics STM32U585.** First-report order code STM32U585OIY6QTR (90-ball WLCSP, reported 4.2 x 3.95 mm, Cortex-M33 at 160 MHz, 2 MB flash, reported 784 kB RAM). Reasons: hardware parallel camera interface (DCMI) with DMA and a hardware crop window; enough RAM for two VGA frames (614,400 bytes, leaving about 184 KiB); reported deep stock at DigiKey; long-established part family. UNVERIFIED: existence of this exact order code, live stock and price, DCMI pin availability on the 90-ball package, usable I/O count, and package height.
- **Radio: Silicon Labs BGM220SC22HNA2** (reel: BGM220SC22HNA2R), a pre-certified Bluetooth LE system-in-package with integrated antenna, run as a network co-processor over UART. US-headquartered maker. UNVERIFIED: live stock and price, the 6 x 6 x 1.1 mm size, and the FCC ID.
- Package note for the STM32U585: the 90-ball WLCSP has 0.4 mm ball pitch and needs an HDI board (microvias in pad). If board area allows, a 0.5 mm-pitch BGA or a 64- or 100-pin LQFP from the same STM32U585 family avoids HDI. Reviewer recollection is that such variants exist (UFBGA132 7 x 7 mm; LQFP64 10 x 10 mm body), but their order codes, I/O counts and DCMI pin-outs are UNVERIFIED and must be read from the ST datasheet. The 48-pin package is not suitable: by reviewer recollection it lacks the port C pins that carry DCMI data bits 0-3.
- Pin budget for this route: the first report's 45 pins plus about 4 for the link to the BLE module (UART TX, RX, module reset, wake) gives about 49. A shift register or LED driver for the eight grain LEDs brings it back to about 44.
- One DCMI port serves two cameras only if the idle sensor releases the bus, or through a bus switch, or by reading the second sensor in a serial mode through an SPI slave port. This is open (section 8).
- Sleep: reviewer recollection of the ST datasheet is that Stop 2 with full RAM retention is about 9 uA, Stop 2 or Stop 3 with 16 kB retained is about 2-4 uA, and Standby with RTC is below 1 uA. The frame buffers do not need to be retained, so a few microamps is reachable. UNVERIFIED.

### Conditional alternate and prototype vehicle: SparkFun Artemis module WRL-15484

Use Artemis development boards with HM01B0 cameras for early algorithm work, because public example code exists. Promote the module back to the production core only if all of the following are shown:

1. SparkFun confirms, in writing, current stock, volume pricing and an end-of-life notice policy.
2. The camera work shows that 320 x 320 is sufficient, or that higher-resolution frames can be captured as cropped strips within 384 kB.
3. A bench test shows the software capture loop reading two sensors reliably, and BLE staying connected across a capture.
4. A pad-level pin assignment fits (the Apollo3 has fixed pad functions; see finding 6).

Mechanical envelope if used (first-report values, UNVERIFIED): 15.5 x 10.5 x 2.3 mm, 0.6 g. Do not print an FCC ID on any label artwork until the ID has been read from the FCC grant.

### Other options, unchanged in order of interest

- u-blox NORA-B106-00B (nRF5340, 512 kB RAM): single certified module, no camera hardware, needs a custom capture driver.
- nRF54LM20A modules (512 kB RAM): re-check once FCC grants and US stock exist.
- Alif Balletto B1 chip-down: best single-chip fit on paper, but needs its own intentional-radiator certification and antenna design.
- Not evaluated by either pass and worth one look before freeze: Espressif ESP32-S3-MINI-1. Reviewer recollection: pre-certified module with BLE 5 and a hardware 8-bit camera port, 15.4 x 20.5 x 2.4 mm, deep sleep about 7 uA, active current tens of milliamps, maker headquartered in China. It is about twice the footprint of the Artemis module. UNVERIFIED.

Do not choose a MIPI CSI-2 camera for this core: none of the options above can receive it (first-report finding; consistent with reviewer recollection; UNVERIFIED).

## 3. Candidates

All specification, price, stock and lifecycle cells are the first report's values. None was re-confirmed against a live source in this pass: treat every cell as UNVERIFIED. The "Reviewer recollection" column records whether the reviewer's memory agrees; it is not a source. Dimensions are L x W x H in mm.

| Name | MPN | Maker / HQ | Key specs (reported) | Dimensions (reported) | Interface / supply (reported) | Price (reported) | US distributors / stock (reported) | Lifecycle (reported) | Reviewer recollection | Verdict after review |
|---|---|---|---|---|---|---|---|---|---|---|
| STM32U585 MCU | STM32U585OIY6QTR | STMicroelectronics / Switzerland | Cortex-M33 160 MHz, 2 MB flash, 784 kB RAM; DCMI camera port (report: from memory) | 90-WLCSP 4.2 x 3.95; height not seen | DCMI, SPI, I2C, ADC, timers, SWD; supply not checked | $8.92 at 1; $5.34 at 1,000 | DigiKey 7,179 (regional page); Future; 13-week lead | Active | Agrees on core, flash, package size and 0.4 mm pitch; ST states 786 kB RAM; family has DCMI; supply 1.71-3.6 V; WLCSP height about 0.6 | Recommended (camera host, design baseline). UNVERIFIED |
| BGM220S BLE SiP | BGM220SC22HNA2 / BGM220SC22HNA2R | Silicon Labs / USA (Texas) | Bluetooth 5.2, integrated antenna, 44-pad module; network co-processor over UART | 6 x 6 x 1.1 (report: from memory) | UART host link; supply not checked | $8.06 at 1; $5.15 at 1,000 | DigiKey 433 to 1,503 by regional page; 16-20 week lead | Active | Agrees on 6 x 6 x 1.1; recalls +6 dBm, 512 kB flash, 32 kB RAM, 1.8-3.8 V, EM2 sleep about 1.4 uA. Recalls a 2026 announcement that Texas Instruments agreed to acquire Silicon Labs; status unknown | Recommended (radio, design baseline). UNVERIFIED |
| SparkFun Artemis module | WRL-15484 | SparkFun / USA (Colorado); SoC Ambiq / USA (Texas) | Apollo3 Blue Cortex-M4F, BLE 5.0, 1 MB flash, 384 kB RAM, up to 48 GPIO, 6 uA/MHz, 1 uA deep sleep; no camera hardware | 15.5 x 10.5 x 2.3, 0.6 g | I2C/SPI masters, ADC, PWM, UART, SWD; supply range not confirmed | $9.95 at 1; no volume breaks seen | SparkFun "In stock" (undated crawl); DigiKey 0; Octopart 0 | Active at SparkFun, informal commitment; retired at several overseas resellers | Agrees on SoC figures, body size and the FCC ID string 2ASW8-ART3MIS; recalls Apollo3 supply 1.755-3.63 V; no knowledge of current stock or price | Conditional alternate and prototype vehicle. UNVERIFIED |
| u-blox NORA-B106 | NORA-B106-00B | u-blox / Switzerland; SoC Nordic / Norway | nRF5340 dual core, 1 MB flash, 512 kB RAM, PCB antenna; no camera hardware | 10.4 x 14.2 x 1.8 (converted from inches) | SPI, I2C, ADC, PWM, UART, SWD | $9.15 at 250 (Richardson RFPD); $8.90 at 500 (Future) | Richardson RFPD; Future (20-week lead); DigiKey status inconsistent | Active as far as seen | Recalls 10.4 x 14.3 x 1.8 in the u-blox data sheet | Viable (single-module alternate). UNVERIFIED |
| nRF54LM20A modules | Raytac AN54LM-20A; Fanstel BM20C; Ezurio 453-00585 / 453-00586 | Raytac / Taiwan; Fanstel / USA; Ezurio / USA; SoC Nordic / Norway | 2 MB NVM, 512 kB RAM, up to 66 GPIO; no camera hardware; no FCC grant confirmed | 9.9 x 13.3 x 2.0; 10.0 x 15.0 x 2.0; 11.0 x 8.0 x 1.8 or 14 x 10 x 2 (sources disagree) | Not checked | Not seen | Not verified | New; Ezurio part in early preview | Agrees on SoC memory and GPIO count | Viable later (watch). UNVERIFIED |
| Ezurio BL54L15 | 453-00001R / 453-00001C; 453-00044C | Ezurio / USA (Ohio) | nRF54L15: 1524 kB RRAM, 256 kB RAM, 31 GPIO, SPIS limited to 8 MHz | 14 x 10 x 1.6 | Not checked | Module price not seen | DigiKey, Mouser, Future list the series | Active | Agrees on SoC figures and module size | Rejected as sole core. UNVERIFIED |
| Ezurio BL54L15u | 453-00223R (453-00224R second antenna variant) | Ezurio / USA | nRF54L15; datasheet preliminary; certification pending | 6.3 x 7.9 x 1.75 | Not checked | About $3.80 (tier unclear) | DigiKey regional page 2,601 | New; certifications pending | No firm recollection | Viable as BLE co-processor once certified. UNVERIFIED |
| Ezurio BL54H20 | 453-00198C | Ezurio / USA | nRF54H20: 1 MB RAM, 2 MB NVM | 13.5 x 10 x 1.8 | Not checked | Not seen | Mouser page exists | Reported end-of-life | No knowledge of the EOL notice | Rejected. UNVERIFIED |
| Silicon Labs BGM240S | BGM240SA22VNA2 / BGM240SA22VNA2R | Silicon Labs / USA | Cortex-M33 78 MHz, 1536 kB flash, 256 kB RAM; no capture hardware | 7 x 7 x 1.18 | Not checked | A$12.59 at 1 (element14 Australia) | Arrow and Mouser list it | Active | Agrees on size and memory; recalls that a "...VNA3" revision exists | Rejected as sole core; usable as co-processor. UNVERIFIED |
| Alif Balletto B1 | AB1C1F4M51820PH0 (also ...HH0) | Alif Semiconductor / USA (California) | Cortex-M55 160 MHz, BLE 5.3, 8-bit parallel camera port, up to 2 MB SRAM, stop 700 nA; no certified module | WLCSP 3.9 x 3.9; FBGA120 6.6 x 6.6 | Not checked | Kits $49.99 and $149; chip price not found | Mouser kits only | Active | Agrees on the SoC description | Viable for a later generation. UNVERIFIED |
| Alif Ensemble E3 | AE302F80F55D5AE-Y / AE302F80F5582LE-Y | Alif / USA | Dual Cortex-M55, MIPI CSI-2, no radio | FBGA194; size not seen | Not checked | $12.05 at 1 (one variant) | Mouser regional pages 148 and 1,640 | Active | - | Rejected (size; no radio). UNVERIFIED |
| Ambiq Apollo510B | AP510BFA-CBR | Ambiq / USA | Cortex-M55 250 MHz, 4 MB flash, 3.75 MB RAM, BLE 5.4, 97 GPIO; no module; no camera port found | 5.6 x 5.6 x 0.8, 153-ball BGA | Not checked | $16.96 at 1 | DigiKey 0 (USD page), 4,935 (UK page); 18-22 week lead | Active, new | Agrees on memory and core | Rejected. UNVERIFIED |
| Ambiq Apollo4 Blue Plus | not confirmed | Ambiq / USA | Cortex-M4 with BLE; no module found | 4.7 x 4.7 BGA | Not checked | Not seen | DigiKey and Mouser pages | Not confirmed | - | Rejected. UNVERIFIED |
| Ambiq Apollo3 Blue Plus | AMA3B2KK-KBR | Ambiq / USA | Cortex-M4F 96 MHz, 2 MB flash, 768 kB RAM, 74 I/O; no module | 108-BGA 5.3 x 4.3 | Not checked | US price not seen | DigiKey 4,065 to 5,213 (regional pages); 16-week lead | Active | Agrees | Viable as chip-down continuity path. UNVERIFIED |
| Raspberry Pi RP2350A + BLE module | RP2350A | Raspberry Pi Ltd / UK | 520 kB SRAM, 30 GPIO, PIO capture, no flash, no radio | QFN-60 7 x 7 | Not checked | $1.10 at 1; $0.80 on reel | Not checked | Active | Agrees; recalls public PIO-based HM01B0 capture libraries for this MCU family | Viable (cheap capture host; sleep current unproven). UNVERIFIED |
| Himax HX6538 (Seeed board) | Seeed 101021112 | Himax / Taiwan; Seeed / China | Dual Cortex-M55, MIPI CSI, no radio | Board 40 x 20 x 10 | Not checked | $15.99 | No DigiKey listing found | Active | - | Rejected. UNVERIFIED |
| u-blox ANNA-B4 | not researched | u-blox / Switzerland | nRF52833, 128 kB RAM (report: from memory) | About 6.5 x 6.5 x 1.2 (report: from memory) | Not checked | Not checked | Not checked | Not checked | Agrees with the from-memory values | Rejected as core. UNVERIFIED |
| STM32WBA / STM32N6 | not researched | STMicroelectronics / Switzerland | WBA: BLE, no camera port; N6: CSI-2, no radio (report: from memory) | Not checked | Not checked | Not checked | Not checked | Not checked | Agrees with the from-memory values | Rejected. UNVERIFIED |
| Espressif ESP32-S3-MINI-1 | not researched by either pass | Espressif / China | Reviewer recollection only: BLE 5 + Wi-Fi, hardware 8-bit camera port, 512 kB SRAM, pre-certified | Reviewer recollection only: 15.4 x 20.5 x 2.4 | Not checked | Not checked | Not checked | Not checked | See cells to the left | Gap: evaluate before freeze. UNVERIFIED |

## 4. Key findings

Confidence here means confidence after this review. "Arithmetic confirmed" means recomputed locally. Input values from datasheets and distributor pages remain UNVERIFIED.

1. **RAM budget.** Two 320 x 320 8-bit frames are 204,800 bytes, leaving 184 KiB of the Artemis module's 384 KiB (179 KiB if the sensor's full 324 x 324 array is read). One VGA frame is 307,200 bytes; two do not fit in 384 KiB or in 512 KiB, and fit in 784 KiB with 184 KiB spare. Arithmetic confirmed. Holding both full frames at once is not strictly required: the scene is static and frames are taken one after the other, so the first frame can be reduced to features before the second is read. Confidence: high for the arithmetic.

2. **GPIO budget.** 18 camera pins on a shared 8-bit bus plus 5 (display), 3 (accelerometer), 10 (grain), 4 (charger and battery), 1 (button) and 4 (debug) is 45. Two separate 8-bit buses give 56, two 4-bit buses 48, two 1-bit ports 42, and a shift register for the grain LEDs saves 5. Arithmetic confirmed. The count is necessary but not sufficient on the Apollo3: see finding 6. Confidence: high for the arithmetic.

3. **Stereo range resolution argues for more than 320 pixels (new in this review).** Focal length in pixels is (width / 2) / tan(HFOV / 2). Disparity is f x B / Z and range error is Z^2 x (disparity error) / (f x B). With B = 30-36 mm and 0.1 pixel disparity error:

   | Image width, lens HFOV | Disparity at 10 m | Range error at 5 m | Range error at 10 m | Range error at 15 m |
   |---|---|---|---|---|
   | 320 px, 60 deg | 0.83-1.00 px | 0.25-0.30 m | 1.0-1.2 m | 2.3-2.7 m |
   | 320 px, 90 deg | 0.48-0.58 px | 0.43-0.52 m | 1.7-2.1 m | 3.9-4.7 m |
   | 640 px, 60 deg | 1.66-2.00 px | 0.13-0.15 m | 0.5-0.6 m | 1.1-1.4 m |
   | 1280 px, 60 deg | 3.3-4.0 px | 0.06-0.08 m | 0.25-0.30 m | 0.56-0.68 m |

   The lens field of view and the 0.1 pixel figure are assumptions, and the stereo self-calibration error adds to it. On these numbers a 320-pixel sensor gives 10-20% range error at 10 m. The processor should therefore not be chosen on the assumption that 320 x 320 is the final resolution. A hardware camera port with a crop window helps here: with the optical axis horizontal, the flagstick and turf horizon sit in a horizontal band, and a 1280 x 200 strip is 256,000 bytes. Confidence: medium (geometry is exact; assumptions are stated).

4. **Supply evidence favours the two-chip route.** By the first report's own figures: Artemis shows 0 at DigiKey and on Octopart and is retired at several overseas resellers, with one undated "In stock" from SparkFun; STM32U585OIY6QTR shows 7,179 and BGM220SC22HNA2 shows 433 to 1,503 at DigiKey regional pages. None of this was re-checked. Confidence: low to medium.

5. **Artemis camera capture is a polled software loop.** Reported by the first agent from the SDK example and forum threads. Reviewer recollection of the driver source agrees: `hm01b0_blocking_read_oneframe` waits on the VSYNC, HSYNC and PCLK pins and reads one byte per pixel clock. A sensor that cannot be slowed to suit this loop cannot be used. UNVERIFIED in this pass. Confidence: medium.

6. **Apollo3 pin functions are fixed per pad (new in this review; reviewer recollection, UNVERIFIED).** ADC inputs, I2C/SPI master pins, timer outputs and SWD each exist only on specific pads. The driver reads the eight data bits through the Apollo3 fast-GPIO register, which by recollection maps pad number modulo 8 to bit position, so D0-D7 need pads with eight different residues. A 45-of-48 count leaves little freedom to satisfy these constraints. A pad-level assignment against the Ambiq datasheet is required before the Artemis module can be called a fit.

7. **BLE during capture.** The first report expects BLE to be idle during a frame. Reviewer recollection is that the Apollo3 Blue radio has its own link-layer controller reached over an internal interface, so a host loop of a few hundred milliseconds would delay events but need not drop the connection. Bench test required. UNVERIFIED. Confidence: low.

8. **Serial-mode capture into an SPI slave is not ruled out by clock rate.** The first report's figure of about 36 MHz for HM01B0 1-bit output at 30 frames/s is consistent with an assumed 376 x 400 total frame (376 x 400 x 30 x 8 = 36.1 MHz). At 5 frames/s the same arithmetic gives 6 MHz, under the 8 MHz SPI-slave limit quoted for the nRF54L15. A static scene tolerates 5 frames/s. The frame timing is an assumption; HM01B0 register values were not checked. Confidence: low.

9. **Price comparison in the first report mixes quantity tiers.** $5.34 + $5.15 = $10.49 is the 1,000-unit sum for the two-chip route; $9.95 is the Artemis single-unit price. At single-unit prices the two-chip route is $8.92 + $8.06 = $16.98. No Artemis volume price was seen. Arithmetic confirmed; inputs UNVERIFIED. Confidence: medium.

10. **"Only certified module with a public HM01B0 capture path" is probably overstated.** Reviewer recollection: ESP32-S3 modules are pre-certified and have a hardware camera port with a vendor camera driver; public PIO-based HM01B0 capture libraries exist for the RP2040/RP2350 family; Arduino boards built on a certified nRF52840 module have a public bit-banged parallel camera library. None was checked in this pass. Confidence: low.

11. **Negative findings carried forward without re-check.** No certified module for Alif Balletto B1, Apollo4 Blue Plus or Apollo510B; Ezurio BL54H20 end-of-life; nRF54L15 and BGM240S limited to 256 kB RAM with no capture hardware; no FCC grant confirmed for nRF54LM20A modules; no certified BLE module with a MIPI CSI-2 receiver. All UNVERIFIED. The reviewer has no recollection that contradicts any of them.

12. **Footprint and height (first-report dimensions, areas recomputed).** Artemis 162.8 mm^2 at 2.3 mm tall. STM32U585 WLCSP90 16.6 mm^2 plus BGM220S 36 mm^2, both about 1.1 mm or less, plus passives and antenna clearance. NORA-B106 about 149 mm^2 at 1.8 mm. A 38 mm circular board is about 1,134 mm^2. The two-chip route is smaller and thinner than any single module considered. Confidence: medium (inputs UNVERIFIED).

## 5. Verification table

Verdict key: confirmed = recomputed or logically checked here; corrected = the report's value or wording needs changing; contradicted = evidence found against it; unverifiable = needs a live source that could not be reached in this pass.

| # | Item | Verdict | Corrected value | Note |
|---|---|---|---|---|
| 1 | SparkFun WRL-15484 exists, is active and purchasable from a US vendor today | unverifiable | - | UNVERIFIED. sparkfun.com blocked. First report's evidence: SparkFun "In stock" (undated), DigiKey 0, Octopart 0, several resellers retired. Reviewer recollection: WRL-15484 is the SparkFun SKU for the Artemis module. |
| 2 | Artemis body 15.5 x 10.5 x 2.3 mm, 0.6 g | unverifiable | - | UNVERIFIED. Matches reviewer recollection of the SparkFun integration guide (retail pages say 10 x 15 mm nominal). |
| 3 | Artemis: Apollo3 Blue, 1 MB flash, 384 kB RAM, BLE 5.0, up to 48 GPIO, 6 uA/MHz, 1 uA deep sleep | unverifiable | - | UNVERIFIED. Matches reviewer recollection of Ambiq and SparkFun figures. |
| 4 | Artemis FCC ID 2ASW8-ART3MIS | unverifiable | - | UNVERIFIED. Matches reviewer recollection. Read the ID from the FCC grant before any label artwork. |
| 5 | Artemis price $9.95 at 1 | unverifiable | - | UNVERIFIED. The first report's summary calls this "verified", but the report could not open sparkfun.com. |
| 6 | Artemis HM01B0 capture is a blocking software read | unverifiable | - | UNVERIFIED in this pass. Reviewer recollection of the driver agrees (polled VSYNC/HSYNC/PCLK, one byte per pixel clock). |
| 7 | Artemis is the only certified module with a public HM01B0 capture path | unverifiable | - | UNVERIFIED and probably overstated; see finding 10. |
| 8 | STM32U585OIY6QTR exists, is active, 7,179 at DigiKey, $8.92 at 1, $5.34 at 1,000 | unverifiable | - | UNVERIFIED. Reviewer recollection: the order code follows ST's scheme (O = 90 balls, I = 2 MB, Y = WLCSP, 6 = -40 to 85 C, Q = internal SMPS, TR = reel). |
| 9 | STM32U585 WLCSP90 is 4.2 x 3.95 mm | unverifiable | - | UNVERIFIED. Matches reviewer recollection, with 0.4 mm pitch and about 0.6 mm height. |
| 10 | STM32U585 has DCMI and the pins are available on WLCSP90 | unverifiable | - | UNVERIFIED. Reviewer recollection: the family has DCMI; the usual 8-bit pin set is on port A, B and C pins that exist on 64-pin packages and larger; the 48-pin package lacks them. Check the ST pin table for the SMPS variant. |
| 11 | STM32U585 RAM 784 kB | unverifiable | - | UNVERIFIED. Reviewer recollection: ST states 786 kB. Either figure holds two VGA frames with about 184-186 KiB spare (computed). |
| 12 | STM32U585 Stop 2 current is "low uA" | unverifiable | - | UNVERIFIED. Reviewer recollection: about 9 uA with full RAM retained, about 4 uA with 16 kB retained, about 2 uA in Stop 3 with 16 kB, under 1 uA in Standby with RTC. A 5 uA target needs reduced RAM retention. |
| 13 | BGM220SC22HNA2 exists, is active, 433 to 1,503 at DigiKey, $8.06 at 1, $5.15 at 1,000 | unverifiable | - | UNVERIFIED. Reviewer recollection: valid Silicon Labs order code (+6 dBm, 512 kB flash, 32 kB RAM). |
| 14 | BGM220S is 6 x 6 x 1.1 mm | unverifiable | - | UNVERIFIED. Matches reviewer recollection of the Silicon Labs datasheet. |
| 15 | BGM220S FCC ID | unverifiable | - | UNVERIFIED. Not given by the first report. Read it from the Silicon Labs datasheet and the FCC grant. |
| 16 | NORA-B106-00B is about 10.4 x 14.2 x 1.8 mm | unverifiable | - | Unit conversion confirmed (0.41 x 0.56 x 0.07 in = 10.41 x 14.22 x 1.78 mm). Reviewer recollection of the u-blox data sheet is 10.4 x 14.3 x 1.8 mm. Use the data-sheet drawing. UNVERIFIED. |
| 17 | Two 320 x 320 frames use 205 kB, leaving about 180 kB of 384 kB; two VGA frames do not fit | confirmed | - | 204,800 bytes; 184 KiB left (179 KiB for 324 x 324). VGA frame 307,200 bytes. Arithmetic only. |
| 18 | GPIO budget: 45 shared bus, 56 separate buses, 48 two 4-bit, 42 two 1-bit, shift register saves 5 | confirmed | - | Arithmetic only. Two-chip route adds about 4 pins for the BLE link (49). Apollo3 pad-function constraints not covered by the count. |
| 19 | Fallback costs about $10.50 at 1,000 "versus $9.95 for one Artemis" | corrected | $10.49 at 1,000 for the pair; $16.98 for the pair at 1; Artemis volume price unknown | The comparison mixes quantity tiers. Inputs UNVERIFIED. |
| 20 | NORA-B106 has 33% more RAM and is 0.5 mm thinner than Artemis; STM32U585 has about double the RAM | confirmed | - | 512/384 = 1.33; 2.3 - 1.8 = 0.5; 784/384 = 2.04. Arithmetic only; inputs UNVERIFIED. |
| 21 | nRF54L15: 256 kB RAM, 1524 kB RRAM, 31 GPIO, SPIS limited to 8 MHz | unverifiable | - | UNVERIFIED. Matches reviewer recollection. Two 320 x 320 frames would leave 56 KiB (computed). |
| 22 | HM01B0 1-bit output at 30 frames/s needs about 36 MHz | unverifiable | - | Consistent with an assumed 376 x 400 total frame. At 5 frames/s the figure is 6 MHz. Sensor timing UNVERIFIED. |
| 23 | Ezurio BL54H20 is end-of-life | unverifiable | - | UNVERIFIED. Reviewer has no knowledge of this notice. |
| 24 | nRF54LM20A: 512 kB RAM, 2 MB NVM; modules exist; no FCC grant confirmed | unverifiable | - | UNVERIFIED. SoC memory matches reviewer recollection. |
| 25 | BGM240S: 7 x 7 x 1.18 mm, 1536 kB flash, 256 kB RAM; no "...VNA3" variant found | unverifiable | - | UNVERIFIED. Size and memory match reviewer recollection. Reviewer recalls that a "...VNA3" revision exists; check before ordering. |
| 26 | Alif Balletto B1: parallel camera port, up to 2 MB SRAM, no certified module, kits only at Mouser | unverifiable | - | UNVERIFIED. SoC description matches reviewer recollection. |
| 27 | Ambiq Apollo3 Blue Plus AMA3B2KK-KBR: 2 MB flash, 768 kB RAM, 5.3 x 4.3 mm BGA | unverifiable | - | UNVERIFIED. Matches reviewer recollection. |
| 28 | No certified BLE module evaluated has a MIPI CSI-2 receiver | unverifiable | - | UNVERIFIED. Consistent with reviewer recollection. |
| 29 | Maker headquarters: SparkFun, Ambiq, Silicon Labs, Ezurio, Alif, Fanstel in the USA; ST and u-blox in Switzerland; Nordic in Norway; Raytac in Taiwan; Raspberry Pi in the UK | unverifiable | - | UNVERIFIED in this pass. All match reviewer recollection. |
| 30 | Condition "cameras stay HM01B0-class, 320 x 320" is compatible with stereo ranging | corrected | Plan for VGA or strip-cropped higher resolution; do not size RAM for 320 x 320 only | Reviewer computation, finding 3: 10-21% range error at 10 m for a 320-pixel image, with stated assumptions. |
| 31 | First-report summary: "Verified figures: ... $9.95", and "recommended" status for Artemis | corrected | Price and stock are unverified; Artemis is conditional on a supply confirmation that has not been obtained | The report itself states sparkfun.com could not be opened and that DigiKey and Octopart show 0. |

## 6. Corrections to the first report

1. Recommendation order. Two-chip route becomes the design baseline; Artemis becomes a conditional alternate and prototype vehicle (section 2).
2. The cost comparison should be like for like (row 19).
3. The price and stock of the Artemis module were not verified (rows 5, 31).
4. The pin budget needs a pad-level assignment on the Apollo3, and four more pins on the two-chip route (finding 6, row 18).
5. The STM32U585 sleep figure should be stated per mode; full-RAM Stop 2 is probably above the 5 uA target (row 12).
6. Use the u-blox data-sheet drawing for NORA-B106 size, not a converted inch figure (row 16).
7. The claim that Artemis is the only certified module with a public camera path should be dropped or qualified, and ESP32-S3 modules should be evaluated or explicitly excluded (finding 10).
8. The 0.4 mm-pitch WLCSP is not the only STM32U585 package; a coarser package should be considered against board area (section 2).

## 7. Risks

1. Nothing in this document was checked against a live source. A part could be obsolete, out of stock or differently dimensioned. This applies to both routes.
2. Artemis is single-source through SparkFun with an informal lifecycle statement, and the first report found no tier-1 distributor stock.
3. Artemis capture is CPU-polled. It limits the sensor clock, has reported field problems, and constrains which pads carry the data bus.
4. 384 kB RAM leaves no room for two VGA frames. Finding 3 suggests 320 x 320 will not be enough for stereo ranging at putt distances.
5. STM32U585 unknowns: DCMI pin availability and I/O count on the chosen package, sleep current with the retention actually needed, and whether ST still lists the exact order code.
6. The 0.4 mm-pitch WLCSP needs an HDI board and tighter assembly process control at a US fabricator and assembler, which raises cost and lead time. A coarser package costs board area.
7. The two-chip route has two firmware images, a host-to-module BLE protocol, and a two-stage firmware update path.
8. One DCMI port for two cameras needs bus sharing, a bus switch, or a serial-mode second channel. Two sensors with the same fixed I2C address need two I2C buses or gated enables.
9. A pre-certified module covers only the intentional radiator. The finished product still needs unintentional-radiator testing, and the module's antenna keep-out, ground-plane and labelling instructions must be followed. A 40 mm board lying on wet turf is a poor antenna environment; range should be measured early.
10. Silicon Labs ownership may be changing (reviewer recollection of a 2026 acquisition agreement with Texas Instruments; UNVERIFIED). This does not affect headquarters country but could affect roadmap and ordering channels.
11. Lead times of 13 to 22 weeks were reported for the ST, Silicon Labs, Ambiq and u-blox parts, from undated regional distributor pages.

## 8. Open questions

1. STM32U585: on the 90-ball WLCSP and on the coarser packages, which DCMI signals are bonded out, how many I/O are usable, what is the package height, and what are the Stop 2, Stop 3 and Standby currents? Is STM32U585OIY6QTR active and in stock at DigiKey, Mouser or Arrow today?
2. BGM220SC22HNA2: confirmed size, supply range, sleep current, FCC ID and ISED ID, antenna layout requirements on a small board, and live US stock.
3. SparkFun Artemis: live stock, volume price, written supply and end-of-life commitment, pad count and pitch, land pattern, antenna keep-out, supply range.
4. Camera: what resolution and lens field of view does the ranging error budget need? This decides RAM and whether a crop window is used.
5. Do the chosen sensors release their data and sync lines in standby, and can their I2C address be changed?
6. How fast can the Apollo3 polled loop read a frame, and does BLE stay connected across it?
7. ESP32-S3-MINI-1: size, sleep current, peak current against the battery, US stock, and whether the non-US maker is acceptable.
8. Is there a US-headquartered radio-less MCU with a parallel camera port and low sleep current that could replace the STM32U585 (for example a small Alif Ensemble part)? Not researched.
9. Alif Balletto B1 bare-chip availability, price and minimum order at US distributors.
10. Status of Apollo3 Blue silicon at Ambiq (active or not recommended for new designs).

## 9. Sources

### 9.1 Pages requested in this verification pass (all failed; no content obtained)

1. https://www.sparkfun.com/sparkfun-artemis-module-low-power-machine-learning-ble-cortex-m4f.html (host not reachable from this session)
2. https://learn.sparkfun.com/tutorials/designing-with-the-sparkfun-artemis/all (host not reachable)
3. https://www.silabs.com/wireless/bluetooth/efr32bg22-series-2-modules/device.bgm220sc22hna (host not reachable)
4. https://www.st.com/en/microcontrollers-microprocessors/stm32u585oi.html (host not reachable)

Four web searches were also refused (search budget exhausted): Artemis stock and price; Artemis FCC ID and dimensions; STM32U585OIY6QTR DCMI and stock; BGM220SC22HNA2 size and FCC ID.

### 9.2 URLs cited by the first report (NOT opened in this pass; listed so a follow-up can re-check them)

5. https://proto-pic.co.uk/content/Artemis_Integration_Guide.pdf
6. https://www.mouser.com/pdfDocs/SparkFunWRL-15484ArtemisBluetoothModule_ProductOverview.pdf
7. https://octopart.com/part/sparkfun/WRL-15484
8. https://community.sparkfun.com/t/product-lifetime-availability-of-artemis-modules-wrl-15484-dev-16401/64311
9. https://core-electronics.com.au/catalog/product/view/sku/WRL-15484
10. https://www.electrokit.com/en/sparkfun-artemis-module
11. https://learn.sparkfun.com/tutorials/programming-the-sparkfun-edge-with-arduino/all
12. https://rust-digger.code-maven.com/src/ambiq-hal-sys-0.1.0/ambiq-sparkfun-sdk/boards_sfe/common/examples/hm01b0_camera_uart/main.c
13. https://community.sparkfun.com/t/camera-demo-stuck-on-read-pclk/45789
14. https://community.sparkfun.com/t/artemis-dev-kit-with-hm01b0-camera-not-capturing-image-using-example1-stopmotion/59656
15. https://www.digikey.com.br/en/products/detail/stmicroelectronics/STM32U585OIY6QTR/18086133
16. https://www.digikey.com.au/en/products/detail/stmicroelectronics/STM32U585OIY6QTR/18086133
17. https://www.digikey.com/en/products/detail/stmicroelectronics/STM32U585CIU6Q/18085577
18. https://futureelectronics.com/p/semiconductors--microcontrollers--32-bit/stm32u585oiy6qtr-stmicroelectronics-1169037
19. https://www.findchips.com/search/bgm220
20. https://www.digikey.sg/en/products/detail/silicon-labs/BGM220SC22HNA2/13169008
21. https://www.digikey.com.br/en/products/detail/silicon-labs/BGM220SC22HNA2R/13169003
22. https://shop.richardsonrfpd.com/Products/Product/NORA-B106-00B
23. https://www.futureelectronics.com/p/semiconductors--wireless-rf--rf-modules-solutions--bluetooth/nora-b106-00b-u-blox-8133422
24. https://www.digikey.ca/en/products/detail/u-blox/NORA-B106-00B/13534376
25. https://docs.zephyrproject.org/latest/build/dts/api/bindings/video/himax,hm01b0.html
26. https://www.nordicsemi.com/Products/nRF54LM20A/Modules
27. https://www.ezurio.com/product/bl54lm20a-series-bluetooth-le-802-15-4-nfc
28. https://www.acalbfi.com/technologies/communications/wireless-connectivity/bluetooth-modules/an54lm-series-bluetooth-6-0-lga-module-nrf54lm20a-based/
29. https://www.cnx-software.com/2025/09/26/nordic-nrf54lm20a-cortex-m33-wireless-mcu-doubles-the-sram-to-512-kb-increases-flash-capacity/
30. https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/keyfeatures_html5.html
31. https://www.ezurio.com/product/bl54l15-series-bluetooth-le-80215-4-nfc
32. https://ezurio.com/product/bl54l15-micro-series-bluetooth-le-802-15-4-nfc
33. https://www.mouser.ca/catalog/specsheets/EZURIO_12-09-2024_453-000-brief.pdf
34. https://azcus.digikey.com/en/products/detail/ezurio/453-00223-K1/26490460
35. https://www.digikey.com/en/product-highlight/e/ezurio/bl54l15u-series
36. https://devzone.nordicsemi.com/f/nordic-q-a/127265/nrf54l15-spis21-slave-receives-correct-rx-amount-but-rx-buffer-is-all-zeros-when-capturing-camera-bf3901-bf30a2-data
37. https://devzone.nordicsemi.com/f/nordic-q-a/95933/how-to-read-a-frame-from-hm01b0-image-sensor
38. https://ezurio.com/product/bl54h20-series-multi-core-bluetooth-le-80215-4-nfc
39. https://www.everythingrf.com/products/rf-modules/ezurio/528-319-bl54h20-series
40. https://au.element14.com/ezurio/453-00198c/bluetooth-module-2-48ghz/dp/4803869
41. https://www.silabs.com/wireless/bluetooth/efr32bg24-series-2-modules/device.bgm240sa22vna
42. https://www.silabs.com/documents/public/data-sheets/bgm240s-datasheet.pdf
43. https://www.arrow.com/ko-kr/products/bgm240sa22vna2r/silicon-labs
44. https://au.element14.com/silicon-labs/bgm240sa22vna2/bluetooth-module-ble-5-3-2mbps/dp/4077940
45. https://alifsemi.com/balletto-b1-series/
46. https://alifsemi.com/download/ADTS0009
47. https://docs.zephyrproject.org/latest/boards/alif/balletto_b1_dk/doc/index.html
48. https://www.edomtech.com/en/product-detail/balletto/
49. https://www.mouser.com/en/new/alif-semiconductor/alif-semi-balletto-b1-kits/
50. https://www.cnx-software.com/2026/09/15/alif-semi-balletto-b1-and-ensemble-e1c-startkits-feature-cortex-m55-ethos-u55-mcu-for-iot-and-edge-ai/
51. https://docs.brilliant.xyz/halo/hardware/
52. https://www.mouser.in/en/c/semiconductors/embedded-processors-controllers/microcontrollers-mcu/arm-microcontrollers-mcu/?series=E3
53. https://www.mouser.ca/newsroom/publicrelations-alif-semi-ensemble-2025final
54. https://www.arrow.com/en/products/ae722f80f55d5as-t/alif-semiconductor
55. https://ambiq.com/product/apollo4-blue-plus/
56. https://ambiq.com/apollo510b/
57. https://www.digikey.com.br/en/products/detail/ambiq-micro-inc/AP510BFA-CBR/28007829
58. https://www.digikey.co.uk/en/products/detail/ambiq-micro-inc/AP510BFA-CBR/28007827
59. https://www.cnx-software.com/2025/09/01/ambiq-apollo510b-ultra-low-power-cortex-m55-edge-ai-mcu-adds-bluetooth-le-5-4/
60. https://www.digikey.co.uk/en/product-highlight/a/ambiq/apollo4-blue-plus-soc
61. https://www.digikey.com.au/en/products/detail/ambiq-micro-inc/AMA3B2KK-KBR/20380327
62. https://www.digikey.hk/en/products/detail/ambiq-micro-inc/AMA3B2KK-KBR/20380327
63. https://www.tomshardware.com/raspberry-pi/raspberry-pi-pico/whats-inside-the-raspberry-pi-pico-2s-rp2350
64. https://datasheets.raspberrypi.com/rp2350/rp2350-product-brief.pdf
65. https://forums.pimoroni.com/t/rp2350-low-power-modes/27235
66. https://www.cnx-software.com/2024/01/19/16-grove-vision-ai-v2-module-features-wiseeye2-hx6538-arm-cortex-m55-ethos-u55-ai-microcontroller/
67. https://botland.store/smart-camera-modules/25285-grove-vision-ai-module-v2-himax-wiseeye2-hx6538-seeedstudio-101021112-5904422386214.html
68. https://electronics-lab.com/grove-vision-ai-v2-features-himax-wiseeye2-and-arm-ethos-u55-micronpu

### 9.3 Local computation

All arithmetic in sections 4 and 5 (RAM budgets, GPIO counts, unit conversion, price sums, footprint areas, pixel-clock estimates, stereo disparity and range error) was recomputed in this pass with a local Python script. No external data entered those computations other than the first report's figures and the stated assumptions.
