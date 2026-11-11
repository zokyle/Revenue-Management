# GreenLine research: feasibility of ground-level (grazing-angle) vision for range, slope and flagstick detection

Date: 2026-11-11

Document type: independent verification of an earlier research report, plus the resulting recommendation.

## 0. Verification status (read this first)

This verification pass could not reach the web. The first report had the same limitation, so nothing in this topic has yet been checked against an external source by either pass.

- Web search: four queries were attempted (Rules of Golf hole definition, Equipment Rules flagstick section, Rule 4.3a, Par Aide flagstick dimensions). All four were refused with "web search budget is used up" (a 200-call limit shared by every agent in this run). No search results were obtained.
- Direct page fetch: `www.usga.org`, `www.randa.org` and `www.paraide.com` all failed to resolve. The session's cloud environment allows only package registries, MCP servers and seven hosts of an unrelated website. No further hosts were tried, as the fetch tool instructs.

Consequences:

- **No rule text, catalogue dimension, literature value or benchmark figure in this document was confirmed against a live source.** Every such item is marked UNVERIFIED. Where the reviewer's own recollection (model training data, up to about mid-2026) agrees or disagrees, that is stated as "reviewer recollection". Recollection is not a source and does not lift an UNVERIFIED mark.
- This topic has no part numbers. Every candidate is a sensing method, an operating mode or a design feature with MPN "n/a", so the check "does the exact MPN exist and is it in stock" does not apply. Three camera parts from the companion document `micro-cameras.md` are listed in section 3 for cross-reference only; they were not verified there either.
- What was verified here: every calculation in the first report was recomputed with two local scripts; the physics behind each derivation was re-derived; the results were compared with the project's own putt model (`sim/greenline_sim/physics.py`) and with the companion documents in this folder. That produced one substantial correction (break sensitivity), a related change to the range requirement, several smaller corrections and several additions (sections 4 to 6).

Hosts that have to be allowed in the session's network settings before the sourced facts can be checked: `www.usga.org`, `www.randa.org`, `www.paraide.com`, the Standard Golf site, and the hosts of the geodesy, atmospheric-optics and tinyML references named in section 9.3.

## 1. Summary

The first report's main conclusion is negative and it survives review: a camera 3-8 mm above the turf sees the green edge-on. It can detect the flagstick, measure its bearing and range it. It cannot see the cup, cannot map the surface between ball and hole, cannot measure far-field cross slope, and cannot deliver 0.2-0.5 mrad absolute elevation. All of the geometry behind these statements was recomputed and is correct.

Results of this review:

1. All stereo, horizon, occlusion, cup-visibility, refraction-geometry and thermal-bending arithmetic is correct to rounding.
2. **The break sensitivity is overstated by a factor of 1.35 to 2.0.** The report used lateral drift = 0.5 x a_y x T^2. That ignores the fact that rolling resistance acts along the velocity vector, so it also removes lateral velocity. The correct small-slope result (closed form, confirmed by numerical integration here and identical to the formula already in the project's putt model) is 4.4-4.9% of putt length per 1% of cross slope for a 3 m putt at Stimpmeter 10 finishing 0.3-0.45 m past the hole, and 6.4% for a putt that dies at the hole. The report gives 6.0-6.8% and 12.8%.
3. With the corrected physics, 1 degree of aim corresponds to 2.7-3.9 mrad (0.27-0.39%) of average cross slope. The restated requirement should be about 3 mrad, not the report's 2-3 mrad and not the original 0.2-0.5 mrad.
4. **Range accuracy matters much less than the report assumes.** On a planar cross slope the aim angle is almost independent of distance. A 10% range error changes the aim by 0.1 degree or less at 2% cross slope; 20% changes it by less than 0.2 degree. The report's "about 3% range" target, and with it the push to focal lengths of 800-1200 px, is not justified by the aim line. A focal length of 500 px or more is enough. The provisional camera in `micro-cameras.md` (reported focal length 657 px) meets that.
5. The mean slope along the putt line needs only about 5-10 mrad accuracy (1% of along-line slope error changes the aim by 0.3-0.7 degree at 2% cross slope). The flagstick-base elevation, which the report rates at 1-2.5 mrad in good geometry and 2-10 mrad one-sided on convex lines, is therefore more useful than the report implies, as an along-line input only.
6. The binding constraint is cross slope. Vision provides none of it. It comes only from the marker's own tilt, which is limited by seating on the turf (estimated 2-9 mrad per placement, unmeasured) and by how well one local sample represents the whole putt (0.75-4.5 mrad at 3 m and 2.5-15 mrad at 10 m for green curvature of 0.5-3% per 10 m).
7. Three statements in the recommendation do not fit the mechanical envelope or need a qualifier: a lens axis 8 mm above the turf is not possible in a puck 7 mm thick; "horizon in the lowest 10-20% of rows" needs the camera tilted up by 16-21 degrees; and the 2.8 mrad thermal figure is relative roll plus 1.5 mrad of common pitch, not yaw.

The recommendation stands with amendments (section 2).

## 2. Final recommendation after review

Status: the engineering reasoning has been re-derived and holds. Sourced inputs (rules, flagstick dimensions, turf facts, literature) are UNVERIFIED.

### 2.1 What the cameras are for

- Use the forward cameras for three things: flagstick detection, flagstick bearing, and range. Add one secondary, confidence-gated input: the elevation of the lowest visible point of the flagstick, used as an upper bound on the mean slope along the putt line.
- Do not promise green mapping, cup detection or far-field cross slope from the ground-level view. Remove the turf-horizon cross-slope path from the firmware plan.
- The flagstick must be in the hole for a camera read. With the flagstick out, the device needs a substitute upright target at the hole, or the user points the marker and enters a distance.
- Bearing is the camera's most valuable output. Bearing error maps one-to-one into aim error, and a hand-pointed 40 mm puck is unlikely to hold a fraction of a degree (reviewer judgment, not measured). Range and along-line slope have loose tolerances (section 2.3).

### 2.2 Camera geometry and ranging

- Focal length: 500 px or more. The 657 px reported for the provisional OVM7692 module is sufficient. Do not move to an 800-1200 px sensor for the sake of the aim line. `micro-cameras.md` and `processor-radio.md` report that the only such candidate is MIPI-only and does not fit the baseline processor (UNVERIFIED).
- Orientation: portrait. Decide the tilt with the mechanical design:
  - Tilted up 16-21 degrees, the horizon sits at 20-10% of the rows and a 2.13 m flagstick is fully in frame from about 2.0-2.3 m. Reviewer estimate of the cost: 0.8-1.0 mm of extra camera-bay height for a cube 2.76 mm long.
  - With the optical axis horizontal, the horizon is at mid-frame and the flagstick top is in frame only beyond about 4.4 m.
- Mount both cameras and the precision accelerometer on one rigid board or stiffener that the printed shell cannot bend. This matches `inertial-sensors.md` and `micro-cameras.md`.
- Stereo: factory calibration held by the rigid mount. Treat the smallest background disparity seen in a read as a bound on calibration drift, not as a zero reference. Sky, or terrain beyond about 1 km, is a valid zero. A tree line at 50-300 m is not.
- Capture: the cameras are read one at a time, so use an interleaved left-right-right-left sequence, at least 16 pairs, and measure disparity on the lowest 0.3-0.5 m of the stick. This cancels linear stick sway.
- Design value for disparity noise: 0.1 px. The 0.05 px used in the report is optimistic for a colour (Bayer) sensor imaging a line about one pixel wide that is narrower than the diffraction blur.
- Fusion: stereo at short range; flagstick angular height with a per-course learned stick height at long range; the same prior as a check on stereo calibration. Show range with an uncertainty and allow manual entry in paces or feet.
- Lens height: as high in the puck as the envelope allows, realistically 3-5 mm above the canopy.

### 2.3 Requirements restated (reviewer derivation, Stimpmeter 10, confirmed numerically)

| Quantity | Tolerance for about 1 degree of aim | Source of the quantity |
|---|---|---|
| Bearing to the hole | Under 0.3 degree; the first report estimates about 1 mrad (0.06 degree) from the camera | Camera |
| Average cross slope along the putt | About 3 mrad (2.7 dying putt, 3.1-3.9 firm putt) | Marker tilt only |
| Mean slope along the line | About 5-10 mrad at 2% cross slope; looser on flatter putts | Marker tilt, plus flagstick-base elevation |
| Range | About 10% (0.1 degree effect at 2% cross slope) | Stereo, stick height, or paces |

The gravity-reference target of 0.2-0.5 mrad in the original concept is tighter than any other term in the chain can use. `inertial-sensors.md` already proposes 1 mrad maximum; that is consistent with this table.

### 2.4 Operating modes

- Quick Read: one placement, planar-green assumption, optional 180 degree spin-and-reread. Suitable for putts up to about 3-6 m depending on contour (section 6.6). Always shown with a confidence indicator.
- Survey: 2-4 placements along the line (ball, midpoint, about 1 m short of the hole) for longer or contoured putts. The numerical check in section 6.5 shows the cross slope is weighted almost evenly along the putt, with less weight on the last half metre for a firm putt, so evenly spaced samples are the right design.
- Flag-out: substitute upright target at the hole, or point-and-enter-distance. A pre-scan from putter-top height remains a possible later addition.

### 2.5 Confidence inputs

Stereo against stick-height range agreement; base elevation against local tilt agreement; fraction of the stick visible; left/right sharpness match (dirty or wet window); sun-in-field flag; frame-to-frame jitter; device temperature rate of change.

### 2.6 Tests before the design is frozen, in priority order

1. Seating repeatability of a 40-44 mm puck on bentgrass and bermudagrass at about 3 mm mowing height, against a long digital level, 30 placements per green.
2. How well a local tilt sample at the ball predicts the average cross slope over 3, 6 and 10 m on real greens (survey with a level or published green contour data).
3. Flagstick disparity repeatability at 3, 6, 10 and 15 m, sun and overcast, with the actual colour sensor.
4. Relative yaw, roll and boresight drift from 5 to 50 C and under a sun lamp.
5. Flagstick-base elevation against surveyed truth on planar, concave and convex lines, and its bias against time of day.

### 2.7 Fallback

If the stereo calibration cannot be held: one forward camera for detection and bearing, range from the learned stick height or from paces, marker tilt and multi-drop survey for slope. Because range tolerance is about 10%, this loses little aim accuracy. It does lose automatic distance on the first putt of a round and on short putts where the stick top is out of frame.

## 3. Candidates

All rows except the last three are methods, modes or design features: there is no part to buy, so MPN, interface, price, distributor and lifecycle are "n/a". The last three rows are carried from `micro-cameras.md` for cross-reference; every catalogue value in them is UNVERIFIED there and here.

| Name | MPN | Maker / HQ | Key specs | Dimensions | Interface / supply | Price | US distributors / stock | Lifecycle | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Stereo ranging of the flagstick, 34 mm baseline, focal length 500 px or more | n/a | method | Error per 0.1 px: f=500 1.8 / 2.9 / 5.9 / 8.8% at 3 / 5 / 10 / 15 m; f=657 1.3 / 2.2 / 4.5 / 6.7%; f=1200 0.7 / 1.2 / 2.5 / 3.7% [recomputed] | Baseline 34 mm from the brief | n/a | n/a | n/a | n/a | Recommended. Amended: 800-1200 px is not needed for the aim line |
| Stereo ranging at f = 170 or 330 px | n/a | method | Error per 0.1 px at 10 m: 17.3% (f=170), 8.9% (f=330) [recomputed] | n/a | n/a | n/a | n/a | n/a | Rejected as the only range sensor; f=330 would still meet a 10% tolerance to about 11 m |
| Monocular ranging by flagstick angular height, stick height learned per course | n/a | method | 2.13 m stick: 141 / 70 / 47 px at 5 / 10 / 15 m (f=330), 280 / 140 / 93 px (f=657) [recomputed]. Hidden base biases range long: +2.8% for 60 mm, +12% for 260 mm | n/a | n/a | n/a | n/a | n/a | Recommended as the long-range complement |
| Mean along-line slope from flagstick-base elevation | n/a | method | Measures the maximum over the path of (z(s) - h)/s: an upper bound on mean slope. Report estimate 1-2.5 mrad in good geometry; one-sided 0.8-10 mrad at 10 m on convex lines [occlusion recomputed] | Lens axis 3-5 mm above canopy | n/a | n/a | n/a | n/a | Fallback / secondary input. Adequate for the 5-10 mrad along-line tolerance in most geometries |
| Far-field cross slope from turf-horizon elevation against azimuth | n/a | method | Collar step 1-2 mrad at 5 m; rough 4-7.5 mrad at 10 m; 1 px = 1.5-3 mrad [recomputed; turf heights UNVERIFIED] | n/a | n/a | n/a | n/a | n/a | Rejected |
| Direct detection of the cup from a stationary camera 5 mm high | n/a | method | Far-wall strip 0.18 mm at 3 m = 0.02 px (f=330), 0.04 px (f=657), 0.07 px (f=1200) [recomputed] | Hole 108 mm (UNVERIFIED) | n/a | n/a | n/a | n/a | Rejected |
| Multi-drop survey mode | n/a | operating mode | Four samples at 5 mrad each over 10 m: 25 mm, 2.5 mrad mean slope [recomputed]. Sampling error not included | n/a | n/a | n/a | n/a | n/a | Recommended |
| Handheld or putter-top pre-scan from 0.85-1.3 m | n/a | operating mode | Cup at 10 m: 3.6 x 0.3 px (f=330), 13 x 1.1 px (f=1200); elevation error about 3.4 cm [recomputed] | n/a | n/a | n/a | n/a | n/a | Fallback for flag-out; not for the first build |
| Classical full-resolution vertical-line detector plus small CNN verifier | n/a | algorithm | 480 x 640 x 15 cycles = 4.6 M cycles: 29 ms at 160 MHz, 36 ms at 128 MHz, 72 ms at 64 MHz [recomputed]. CNN timing UNVERIFIED | 64 x 480 ROI = 31 kB | n/a | n/a | n/a | n/a | Recommended |
| Reference target: regulation flagstick | n/a | Par Aide Products Co. / USA (Minnesota); Standard Golf Company / USA (Iowa); both reviewer recollection, UNVERIFIED | 7, 7.5, 8 ft; 1/2 in diameter; tapered tournament versions. All UNVERIFIED | About 12.7 mm x 2130-2440 mm, UNVERIFIED | n/a | Not researched | Sold direct and through golf-course supply dealers, UNVERIFIED | UNVERIFIED | Viable as the target; buy samples for the test rig |
| AR and oleophobic coated sapphire window under a brow | n/a | design feature | Uncoated sapphire reflects 7.7% per surface, 14.9% for two [recomputed, n = 1.77 UNVERIFIED] | Set by the camera module | n/a | Not researched | Not researched | n/a | Viable; sourcing belongs to the optics topic |
| Cross-reference: OVM7692 CameraCubeChip (provisional primary in `micro-cameras.md`) | OVM7692-RYAA | OmniVision / USA, Chinese parent (reviewer recollection) | 640 x 480, 1.75 um, EFL 1.15 mm, F/3.0; f = 657 px. All UNVERIFIED | 2.95 x 3.47 x 2.76 mm, UNVERIFIED | 8-bit DVP, SCCB, 2.8 V, UNVERIFIED | 27.50 at 1; 6.25 at 2,500, UNVERIFIED | DigiKey, stock UNVERIFIED | UNVERIFIED | Meets the 500 px requirement of this document |
| Cross-reference: OVM9724 CameraCubeChip | OVM9724-RADA | OmniVision / USA | 1280 x 720, 1.4 um, EFL 1.6 mm; f = 1143 px. All UNVERIFIED | 3.9 x 2.9 x 2.4 mm, UNVERIFIED | MIPI CSI-2 only, UNVERIFIED | 4.57 at 3,000, UNVERIFIED | DigiKey non-stock, UNVERIFIED | Conflicting, UNVERIFIED | Not required by this document's findings |
| Cross-reference: Himax HM01B0 module | HM01B0-MNA-00FT870 | Himax / Taiwan | 320 x 320, 3.6 um, EFL 0.66 mm; f = 183 px. All UNVERIFIED | 5.0 x 5.0 mm holder, UNVERIFIED | DVP, I2C, UNVERIFIED | 12.33 at 1, UNVERIFIED | DigiKey, UNVERIFIED | UNVERIFIED | Below the 500 px requirement |

## 4. Key findings, with confidence

"High" is used only for results recomputed here from stated assumptions. Anything that rests on a rule, catalogue or paper is UNVERIFIED.

1. **The green is seen edge-on.** From a lens 5 mm above the canopy, all turf beyond h x f lies in the first pixel row below the horizon: 0.85 m (f=170), 1.65 m (f=330), 2.5 m (f=500), 3.3 m (f=657), 6.0 m (f=1200). From 3 mm the figures are 40% smaller. The surface between ball and hole cannot be mapped from this viewpoint. Confidence: high (geometry).
2. **The cup cannot be seen; the flagstick is the only target.** The visible strip of far cup wall is 0.18 mm at 3 m, which is 0.02-0.07 px for any focal length considered. Confidence: high for the geometry. The 108 mm hole diameter is UNVERIFIED and agrees with reviewer recollection.
3. **Gentle convexity hides the base of the flagstick.** Visible-turf horizon sqrt(2 R h) is 1.8-4.5 m for slope changes of 3-0.5% per 10 m at h = 5 mm. Hidden base at 10 m: 8, 23, 60, 100 mm (0.8, 2.3, 6.0, 10.0 mrad). At h = 3 mm: 11, 29, 68 mm for 0.5, 1, 2% per 10 m. The measured base elevation is an upper bound on mean slope. Confidence: high (geometry). How common such curvature is on real putt lines is UNVERIFIED.
4. **Stereo range error** follows dZ = Z^2 x sigma_d / (f x B). All figures in the report are correct. Confidence: high.
5. **Using far background as zero disparity biases range long** by 1 / (1 - Z/Z_bg) - 1, independent of camera. The report's first-order values are slightly low at long range (section 5, item 12). Confidence: high.
6. **Relative yaw must be known to 0.04-0.3 mrad for 0.05 px** (0.076 mrad, 2.6 um across 34 mm, for f=657 px; twice that for 0.1 px). Yaw error produces almost no vertical disparity (under 0.01 px at the image corner), so it cannot be recovered from epipolar geometry alone. Confidence: high (geometry). The cited self-calibration literature is UNVERIFIED.
7. **Break sensitivity, corrected.** At Stimpmeter 10 with no slope along the line, the aim offset per 1% of cross slope is 6.4% of putt length (3.65 degrees) for a dying putt, and 4.4-4.9% (2.5-2.8 degrees) at 3 m or 5.5-5.7% (3.1-3.3 degrees) at 10 m for a putt finishing 0.3-0.45 m past. Confidence: high (closed form, numerical integration, and agreement with `sim/greenline_sim/physics.py`). The Stimpmeter release speed of 1.83 m/s is UNVERIFIED and agrees with reviewer recollection.
8. **Aim is insensitive to range.** At 2% cross slope a +10% range error changes the aim by +0.10 degree at 3 m and +0.05 degree at 10 m. Confidence: high for the planar model.
9. **Aim depends moderately on along-line slope.** At 2% cross slope, a 1% error in along-line slope changes the aim by 0.3-0.5 degree at Stimpmeter 10 and 0.5-0.7 degree at Stimpmeter 12. Downhill is the more sensitive direction. Confidence: high for the planar model.
10. **Cross slope is weighted almost evenly along the putt.** A section of cross slope at distance s contributes in proportion to (L - s) / (L + past - s). For a 3 m putt finishing 0.3 m past, the first, middle and last thirds contribute 39%, 36% and 25%. For a dying putt the weighting is uniform. A tilt sample at the ball is therefore as relevant as a sample anywhere else, but it is one sample of a path average. Confidence: high (derivation confirmed numerically).
11. **Grazing-ray refraction is of the same order as the original 0.2-0.5 mrad target.** dn/dT is -0.86 ppm/K at 30 C; a ray at constant height in a gradient of 100 / 200 / 500 K/m is bent 0.43 / 0.86 / 2.14 mrad over 10 m. Arithmetic confirmed. The gradient magnitudes at 3-8 mm above irrigated turf are estimates with no source. Reviewer estimate: a canopy-to-screen-height difference of 3-9 K under a log profile gives 0.2-1.1 mrad at 10 m for a lens 4-8 mm up, so the report's 0.3-2 mrad is plausible, with its upper end more likely on dry or dormant turf. Confidence: high for the optics, low for the magnitudes.
12. **Shimmer adds random jitter that averaging can reduce.** The report's formula is the plane-wave, two-axis form (reviewer recollection, UNVERIFIED). For a target 10 m away the spherical-wave, single-axis value is about 0.43 times smaller, but the turbulence strength at 5 mm could be ten times the report's assumption. Net: about 0.02-0.3 mrad per frame. Confidence: low.
13. **The turf horizon is not a cross-slope sensor.** It is formed by the collar, rough and surrounds. Confidence: medium (reasoning sound; turf heights UNVERIFIED).
14. **Thermal gradients in a printed shell move the cameras by milliradians.** A 5 K through-thickness difference in a 6 mm nylon shell gives 2.8 mrad of relative roll between the cameras and 1.5 mrad of common pitch relative to the centre. A 3 K front-to-back difference gives 0.26 mrad of relative yaw. For the same geometry and temperature differences in FR-4 the figures are 0.43, 0.23 and 0.04 mrad, and a thin board carries a much smaller through-thickness difference. Confidence: high for the arithmetic; expansion coefficients are reviewer recollection.
15. **Marker seating is probably the largest single error and is unmeasured.** 0.1-0.35 mm across 40 mm is 2.5-8.75 mrad. `inertial-sensors.md` estimates 2-5 mrad. No published data was found by any pass. Confidence: low for the number, medium for the conclusion.
16. **Hole, flagstick and green facts** (hole 4.25 in by at least 4 in; flagstick at most 0.75 in near the surface; typical sticks 7-8 ft and 1/2 in; mowing height 2.5-4 mm; green size; hole-location slopes) are UNVERIFIED. All agree with reviewer recollection. One addition from recollection, UNVERIFIED: the nominal flagstick length includes the part seated in the cup, so the height visible above the turf is roughly 0.15-0.18 m less than nominal.
17. **Rules status.** The report's statement that the device is probably practice-only is consistent with `rules-compliance.md`. UNVERIFIED in both.

## 5. Verification table

Verdicts: confirmed = recomputed or re-derived in this pass; corrected = an error or omission found by derivation; unverifiable = needs a live source that could not be reached. Nothing is marked contradicted.

| # | Item | Verdict | Corrected or added value | Note |
|---|---|---|---|---|
| 1 | The first report's statement that no web source was reachable | confirmed | | Same result here: search budget exhausted, three hosts unresolvable. |
| 2 | Candidate (recommended): stereo ranging at f = 500 or 1200 px, with "ideally 800-1200 px" | corrected | 500 px or more is sufficient; 657 px (provisional OVM7692) gives 1.3 / 2.2 / 4.5 / 6.7% per 0.1 px at 3 / 5 / 10 / 15 m | No MPN. Arithmetic confirmed. The higher focal length is not needed because aim tolerates about 10% range error (item 21). |
| 3 | Candidate (recommended): monocular stick-height ranging, "about 2-3% from 5 to 15 m" | confirmed | Holds on planar or concave lines only. Hidden base adds +2.8% (60 mm) to +12% (260 mm) | No MPN. Pixel counts confirmed. See also items 14 and 15. |
| 4 | Candidate (fallback): mean slope from flagstick-base elevation | confirmed | | No MPN. Upper-bound property re-derived. Its accuracy is adequate for the 5-10 mrad along-line tolerance; it gives no cross-slope information. |
| 5 | Candidate (recommended): multi-drop survey, 25 mm and 2.5 mrad over 10 m | confirmed | | No MPN. Arithmetic confirmed. Does not include the error of using four point samples to represent 10 m. |
| 6 | Candidate (fallback): handheld pre-scan, cup 3.6 x 0.3 px and 13 x 1.1 px, 3.5 cm | confirmed | 3.4 cm | No MPN. Arithmetic confirmed. |
| 7 | Candidate (recommended): classical detector plus CNN verifier; 36 ms at 128 MHz, 70 ms at 64 MHz | confirmed | 72 ms at 64 MHz; 29 ms at 160 MHz | No MPN. Arithmetic only. The 15 cycles per pixel and all CNN timings are estimates. Reviewer recollection, UNVERIFIED: the MLPerf Tiny reference result for the 96 x 96 visual-wake-words network on a 120 MHz Cortex-M4 board was about 0.6 s, consistent with the report's range. |
| 8 | Stereo error table (f = 170, 330, 500, 1200; 0.05 px) and disparities at 10 m | confirmed | | All values reproduced. |
| 9 | Reach for 3% range: f=170 to 3 m, f=330 to 6 m, f=500 to 10 m | confirmed | 3.5 / 6.7 / 10.2 / 24.5 m | Correct, but the 3% requirement itself is not supported (item 21). |
| 10 | Disparity precision 0.02-0.1 px on the flagstick; cited sub-pixel literature | unverifiable | Use 0.1 px as the design value | Literature not opened. Reviewer recollection agrees that the cited papers exist. The report does not account for the Bayer mosaic or for diffraction (reported Airy diameter about 2.3 px on the OVM7692). |
| 11 | Yaw tolerance 0.29 / 0.15 / 0.10 / 0.042 mrad and 10 / 5.2 / 3.4 / 1.4 um; vertical disparity "0.005 px for 0.15 mrad at f=330" | confirmed | 0.0087 px at the corner of a 320 x 240 image; 0.005 px at mid-field | Conclusion unchanged: yaw is not observable from vertical disparity. |
| 12 | Background-as-infinity bias "3 / 5 / 10 / 15% at 100 m; 6-30% at 50 m" | corrected | Exact: 3.1 / 5.3 / 11.1 / 17.6% at 100 m; 6.4 / 11.1 / 25.0 / 42.9% at 50 m; 1.0 / 1.7 / 3.4 / 5.3% at 300 m | The report used the first-order form Z/Z_bg. Its own summary formula is the exact one. |
| 13 | "Infinity" to 0.05 px starts at 116 / 224 / 340 / 816 m | confirmed | 447 m for f=657 | |
| 14 | "Learn the stick length on the first short putt where stereo is good (0.4-1.3% at 2-3 m)" | corrected | Possible only with the camera tilted up 16-21 degrees. With a horizontal axis in portrait the top is in frame beyond 4.4 m, where stereo is 2.0-2.7% per 0.1 px at f=657 | The top of a 2.13 m stick is 35.4 degrees up at 3 m and 23.1 degrees at 5 m (confirmed). |
| 15 | "Mount it portrait with the horizon in the lowest 10-20% of rows" | corrected | Needs an up-tilt of 21.3 / 18.8 / 16.3 degrees for 10 / 15 / 20% (f=657, 640 rows). Stick fully in frame beyond 1.97 / 2.15 / 2.34 m. About 0.8-1.0 mm more bay height (reviewer estimate) | Not compatible with "optical axis horizontal" in the brief. A decision for the mechanical design. |
| 16 | Stick width and height in pixels; 1 px end error 0.7 / 1.4 / 2.1% | confirmed | Visible height is probably 0.15-0.18 m less than nominal length (reviewer recollection, UNVERIFIED) | Does not matter if the height is learned per course. |
| 17 | Refraction: dn/dT about -0.86 ppm/K; errors at 100 / 200 / 500 K/m; log-law cases; mirage angle and distance | confirmed | For visible light the coefficient is about 2% larger (-0.87 ppm/K) | Arithmetic and optics confirmed. Gradient magnitudes are unsourced estimates. The log law is not strictly valid this close to the canopy. |
| 18 | "Raising the lens from 4 to 8 mm halves the error" | corrected | 8 mm is outside a puck of 7 mm or less. Realistic range is 3-5 mm: 1.5 times less refraction error and 1.22 times more convex horizon going from 3 to 4.5 mm | The scaling is right under the 1/z assumption. |
| 19 | Levelling practice keeps sight lines at least 0.5 m above ground; refraction coefficient from about -4 to +16 near the ground; Kukkamaki exponent -1/3 | unverifiable | | Not opened. All three agree with reviewer recollection. The conversion of k = -4 to -0.755 K/m, and to about -270 K/m at 5 mm under 1/z scaling, was recomputed. |
| 20 | Shimmer: sigma^2 = 2.91 Cn2 L D^(-1/3); 38-209 urad | unverifiable | Spherical-wave single-axis values are 0.43 times the report's; turbulence strength at 5 mm may be 10 times higher. Net 0.02-0.3 mrad per frame | Arithmetic confirmed. Formula form and Cn2 values are reviewer recollection. The aperture is smaller than the likely inner scale, so the formula is at the edge of validity. |
| 21 | Range requirement "about 3%" (implicit in the stereo conclusions and the 800-1200 px recommendation) | corrected | About 10% is sufficient for the aim line: +10% range error changes aim by 0.04-0.10 degree at 2% cross slope over 3-15 m; +20% by 0.07-0.19 degree | Reviewer derivation with the planar model. Range still enters pace advice one-to-one. |
| 22 | Break sensitivity "6.0-6.8% of putt length per 1% cross slope (3.4-3.9 degrees); 12.8% (7.3 degrees) dying" | corrected | 4.4-4.9% (2.5-2.8 degrees) at 3 m finishing 0.3-0.45 m past; 6.4% (3.65 degrees) dying; 5.5-5.7% at 10 m firm | The report's formula omits the damping of lateral velocity by rolling resistance. Confirmed by closed form, numerical integration and the project's putt model. Overstatement 1.35-2.0 times. |
| 23 | "Half a cup at 3 m corresponds to about 0.26% slope"; "1 degree is about 0.15-0.3% slope"; requirement "about 2-3 mrad" | corrected | Half a cup at 3 m: 0.37-0.41% firm, 0.28% dying. One degree: 0.27% dying, 0.31-0.39% firm. Requirement: about 3 mrad | Follows from item 22. |
| 24 | Edge-on geometry: first-row distances 0.85 / 1.65 / 2.5 / 6.0 m | confirmed | 3.3 m for f=657; 2.0 m for f=657 at h = 3 mm | |
| 25 | Convex horizon and hidden base (R = 2000 to 333 m) | confirmed | | All values reproduced. Added: 260 mm hidden at 15 m is 17.4 mrad; at h = 3 mm the hidden base at 10 m is 11 / 29 / 68 / 111 mm. |
| 26 | Cup visibility figures | confirmed | | Geometry confirmed; hole diameter UNVERIFIED. |
| 27 | Turf-horizon contamination: collar 1-2 mrad, rough 4-7.5 mrad, 1 px = 2-3 mrad | confirmed | 1 px = 1.5 mrad at f=657 | Arithmetic only. Collar and rough heights UNVERIFIED. |
| 28 | Thermal bending: "5 K top-to-bottom bends a nylon shell 2.8 mrad across the baseline" (stated under yaw); "3 K side-to-side gives 0.26 mrad" | corrected | Through-thickness gradient: 2.8 mrad relative roll plus 1.5 mrad common pitch at 18 mm radius. Relative yaw comes from a front-to-back gradient, 0.26 mrad for 3 K over 40 mm | Magnitudes confirmed; the axis assignment was wrong. Relative roll shifts horizontal disparity by roll x vertical offset: 0.28-0.56 px at 100-200 px. Roll is observable from the stick's own image; yaw is not. Design consequence unchanged. |
| 29 | "1 um lens shift is about 0.3 px for 3-3.6 um pixels" and 0.8 mrad | confirmed | 0.57 px for the 1.75 um pixels reported for the OVM7692 | |
| 30 | Stick sway: 5 mm at 10 m is 0.17 px at f=330 | confirmed | 0.33 px at f=657. With a 33 ms left-right offset and 1.5 Hz sway the error is 0.04 px on the lowest 0.4 m and 0.10 px at 1 m height | Interleaved L-R-R-L capture cancels the linear part. |
| 31 | Outdoor imaging: hyperfocal 143 mm; sapphire 7.7% per surface, about 15% total | confirmed | | Refractive index and hardness values are reviewer recollection. |
| 32 | "A 0.5 mm droplet covers 6-25% of a 1-2 mm aperture" | corrected | With the reported 0.38 mm entrance pupil and a window 1-2.5 mm ahead, one 0.5 mm droplet fully covers a patch 3-7 degrees wide and degrades 20-50 degrees of the field | The droplet sits on the window, not at the pupil, so it corrupts a region of the image and may hide the flagstick entirely. Reviewer derivation from UNVERIFIED lens data. |
| 33 | Seating estimate 3-9 mrad from 0.1-0.35 mm across 40 mm | unverifiable | Arithmetic gives 2.5-8.75 mrad | No measurement exists. Consistent in order with the 2-5 mrad estimate in `inertial-sensors.md`. |
| 34 | Hole 4.25 in diameter, at least 4 in deep, liner at least 1 in down | unverifiable | | Agrees with reviewer recollection. |
| 35 | Flagstick limits: circular, at most 2 in above 3 in from the surface, at most 0.75 in from 3 in above to 3 in below; height at least 7 ft recommended | unverifiable | | Agrees with reviewer recollection. Section numbering not checked. |
| 36 | Par Aide and Standard Golf: 7, 7.5, 8 ft; 1/2 in; tapered tournament sticks; 14 x 20 in flags | unverifiable | | Agrees in outline with reviewer recollection. Confirm from catalogues before fixing detector assumptions. |
| 37 | Green facts: mowing 2.5-4 mm; collar, fairway and rough heights; green 5,000-6,000 sq ft; hole-location slope limits; Stimpmeter speeds | unverifiable | | Agrees with reviewer recollection. |
| 38 | Stimpmeter 10 ft = 0.549 m/s^2 | confirmed | | 1.83^2 / (2 x 3.048). Same constant as the project's putt model. Release speed UNVERIFIED. |
| 39 | Rule 13.2a (flagstick may stay in since 2019); Rule 4.3 makes the device practice-only | unverifiable | | Agrees with reviewer recollection and with `rules-compliance.md`. |
| 40 | Error budget for mean slope: 1-1.5 mrad overcast, 1.5-2.5 mrad sun, plus 0.8-10 mrad one-sided on convex lines | confirmed | Add 0.1-0.33 mrad for 1 mm uncertainty in lens height above the canopy (10 m and 3 m) | Root-sum-square of the report's own terms reproduces the totals. Inputs are estimates. |
| 41 | Consistency with `micro-cameras.md`, `inertial-sensors.md`, `processor-radio.md` | confirmed | | Focal lengths, yaw tolerance, bias table, cup invisibility, thermal bow and the rigid-board requirement agree across documents. |

## 6. Recomputed numbers

### 6.1 Stereo range error, baseline 34 mm (percent of range)

| Focal length (px) | 0.05 px: 3 / 5 / 10 / 15 m | 0.1 px: 3 / 5 / 10 / 15 m | Disparity at 10 m (px) |
|---|---|---|---|
| 170 | 2.6 / 4.3 / 8.7 / 13.0 | 5.2 / 8.7 / 17.3 / 26.0 | 0.58 |
| 330 | 1.3 / 2.2 / 4.5 / 6.7 | 2.7 / 4.5 / 8.9 / 13.4 | 1.12 |
| 500 | 0.9 / 1.5 / 2.9 / 4.4 | 1.8 / 2.9 / 5.9 / 8.8 | 1.70 |
| 657 | 0.7 / 1.1 / 2.2 / 3.4 | 1.3 / 2.2 / 4.5 / 6.7 | 2.23 |
| 1143 | 0.4 / 0.6 / 1.3 / 1.9 | 0.8 / 1.3 / 2.6 / 3.9 | 3.89 |
| 1200 | 0.4 / 0.6 / 1.2 / 1.8 | 0.7 / 1.2 / 2.5 / 3.7 | 4.08 |

Range out to which the error stays within 10% at 0.1 px: 5.8 m (f=170), 11.2 m (f=330), 17.0 m (f=500), 22.3 m (f=657).

### 6.2 Range bias when scenery at Z_bg is taken as zero disparity

| True range | Z_bg = 50 m | Z_bg = 100 m | Z_bg = 300 m |
|---|---|---|---|
| 3 m | +6.4% | +3.1% | +1.0% |
| 5 m | +11.1% | +5.3% | +1.7% |
| 10 m | +25.0% | +11.1% | +3.4% |
| 15 m | +42.9% | +17.6% | +5.3% |

### 6.3 Break on a planar cross slope, Stimpmeter 10, no slope along the line

Aim offset at the hole per 1% of cross slope, as a percentage of putt length and in degrees.

| Putt length | Pace | Report's formula | Corrected | Ratio |
|---|---|---|---|---|
| 3 m | dies at hole | 12.75% (7.31 deg) | 6.38% (3.65 deg) | 2.00 |
| 3 m | 0.30 m past | 6.84% (3.92 deg) | 4.85% (2.78 deg) | 1.41 |
| 3 m | 0.45 m past | 5.98% (3.43 deg) | 4.43% (2.54 deg) | 1.35 |
| 10 m | 0.30 m past | 9.03% (5.18 deg) | 5.70% (3.27 deg) | 1.59 |
| 10 m | 0.45 m past | 8.37% (4.79 deg) | 5.47% (3.14 deg) | 1.53 |
| 15 m | 0.30 m past | 9.62% (5.51 deg) | 5.87% (3.37 deg) | 1.64 |

Corrected closed form: aim = (5/14) g s / a x F, with F = 1 + rho^2 ln(rho^2) / (1 - rho^2) and rho^2 = past / (distance + past). This is the function `planar_break_angle_paced` in `sim/greenline_sim/physics.py`.

### 6.4 Sensitivity of the aim to the other inputs (2% cross slope, 0.3 m past)

| Input error | Effect on aim at 3 m | Effect on aim at 10 m |
|---|---|---|
| Range +3% | +0.03 deg | +0.02 deg |
| Range +10% | +0.10 deg | +0.05 deg |
| Range +20% | +0.19 deg | +0.10 deg |
| Along-line slope 0.5% too uphill, Stimpmeter 10 | -0.17 deg | -0.21 deg |
| Along-line slope 1% too uphill, Stimpmeter 10 | -0.32 deg | -0.40 deg |
| Along-line slope 1% too downhill, Stimpmeter 10 | +0.37 deg | +0.46 deg |
| Along-line slope 1% too downhill, Stimpmeter 12 | +0.54 deg | +0.66 deg |
| Cross slope 0.3% (3 mrad) | 0.83 deg | 0.98 deg |

### 6.5 Where along the putt the cross slope matters

3 m putt, 1% cross slope applied to one third of the path only (numerical integration; the analytic weight (L - s) / (2a (L + past - s)) gives the same values).

| Pace | First third | Middle third | Last third | Whole putt |
|---|---|---|---|---|
| Dies at hole | 64 mm | 64 mm | 63 mm | 189 mm |
| 0.30 m past | 57 mm | 53 mm | 36 mm | 145 mm |
| 0.45 m past | 54 mm | 49 mm | 30 mm | 133 mm |

### 6.6 Error from using the local cross slope at the ball for the whole putt

If the cross slope changes linearly along the line, the local value at the ball differs from the path average by half the change.

| Slope change per 10 m | 2 m putt | 3 m putt | 5 m putt | 10 m putt |
|---|---|---|---|---|
| 0.5% | 0.5 mrad | 0.75 mrad | 1.25 mrad | 2.5 mrad |
| 1.0% | 1.0 mrad | 1.5 mrad | 2.5 mrad | 5.0 mrad |
| 2.0% | 2.0 mrad | 3.0 mrad | 5.0 mrad | 10.0 mrad |
| 3.0% | 3.0 mrad | 4.5 mrad | 7.5 mrad | 15.0 mrad |

Against a 3 mrad tolerance, a single placement is adequate to about 6 m on gently contoured greens (1% per 10 m) and to about 3 m on moderately contoured ones (2% per 10 m), before seating error is added.

### 6.7 Portrait framing for a 657 px, 640-row camera

| Horizon position (rows from bottom) | Up-tilt | Top row elevation | 2.13 m stick fully in frame beyond |
|---|---|---|---|
| 50% (axis horizontal) | 0 deg | 26.0 deg | 4.37 m |
| 20% | 16.3 deg | 42.3 deg | 2.34 m |
| 15% | 18.8 deg | 44.8 deg | 2.15 m |
| 10% | 21.3 deg | 47.3 deg | 1.97 m |

### 6.8 Occlusion by a convex green

| Slope change per 10 m | Horizon, h = 3 / 5 / 8 mm | Hidden base at 10 m, h = 3 / 5 / 8 mm | Hidden base at 15 m, h = 5 mm |
|---|---|---|---|
| 0.5% | 3.5 / 4.5 / 5.7 m | 11 / 8 / 5 mm | 28 mm |
| 1.0% | 2.4 / 3.2 / 4.0 m | 29 / 23 / 18 mm | 70 mm |
| 2.0% | 1.7 / 2.2 / 2.8 m | 68 / 60 / 51 mm | 163 mm |
| 3.0% | 1.4 / 1.8 / 2.3 m | 111 / 100 / 89 mm | 260 mm |

### 6.9 Refraction (optics confirmed; gradients are estimates)

| Vertical temperature gradient at ray height | Curvature | Elevation error at 3 / 5 / 10 / 15 m | Distance beyond which flat turf is below the optical horizon, h = 5 mm |
|---|---|---|---|
| 60 K/m | 51 urad/m | 0.08 / 0.13 / 0.26 / 0.39 mrad | 14 m |
| 100 K/m | 86 urad/m | 0.13 / 0.21 / 0.43 / 0.64 mrad | 11 m |
| 200 K/m | 171 urad/m | 0.26 / 0.43 / 0.86 / 1.28 mrad | 7.6 m |
| 500 K/m | 428 urad/m | 0.64 / 1.07 / 2.14 / 3.21 mrad | 4.8 m |

## 7. Risks

1. Verification gap. Neither pass opened a source. Rules, flagstick dimensions, turf facts, literature values and benchmark timings could be wrong or out of date.
2. Cross slope is not observable by the cameras. The aim line depends on the marker's own tilt and on how well that one sample represents the putt. If seating repeatability on real turf is worse than about 3 mrad, a single-placement read cannot meet a 1 degree aim target on any putt.
3. Flagstick out of the hole. No camera target exists, and the cup cannot be found from the ground.
4. Convex lines hide 8-260 mm of the flagstick base at 10-15 m. The device cannot tell this from a planar green by vision. The along-line slope then reads too far uphill, which makes the computed break too small. The same occlusion biases stick-height range long by up to 12%.
5. Stereo calibration. A relative yaw of 0.15 mrad (5 um across 34 mm) is the whole 0.1 px budget at 657 px. Sun on one side of a plastic puck can exceed this within a minute unless the cameras share a rigid board.
6. Zero-disparity reference. Tree lines at 50-150 m bias range long by 5-43% at 5-15 m if used as infinity.
7. Sequential capture. Without interleaving, stick sway and flag flutter appear as disparity error of 0.1-0.3 px.
8. Refraction in strong sun lowers the apparent flagstick base by a few tenths of a milliradian to about 2 mrad at 10 m, with the opposite sign in evening inversions. Magnitudes are unsourced.
9. Wet or dirty window. A single 0.5 mm droplet can blank the part of the image that holds the flagstick. Dew is present on most greens in the morning. Coatings wear in a pocket.
10. Detection margin. The flagstick is about 0.8 px wide at 10 m on the provisional camera, narrower than the diffraction blur, on a colour-mosaic sensor. Detection depends on integrating along its length and on contrast against the background. Untested.
11. False detections: tree trunks, another green's flagstick, legs, rakes, club shafts.
12. Mechanical conflict. The up-tilt that makes stick-height ranging work at short range costs about 1 mm of camera-bay height in a device whose thickness target is 7 mm or less.
13. Flagstick variation. Length, diameter, colour and striping vary by course and vendor; a course may mix lengths or use short pins on practice greens, where a practice-only device will mostly be used.
14. Model risk. The break figures use a planar surface and a constant rolling deceleration. Grain, wobble at low speed and non-planar surfaces are not included.
15. Rules. The device is very probably not usable in a round under the Rules of Golf (see `rules-compliance.md`). UNVERIFIED.

## 8. Open questions

1. Measured seating repeatability of a 40-44 mm puck on real greens, by grass type, mowing height and firmness. Does a spin-and-reread halve it?
2. How well does a local tilt sample predict the path-average cross slope on real greens at 3, 6 and 10 m? Published green contour data could answer this without field work.
3. How often are putt lines convex over 5-15 m, and by how much?
4. Actual temperature gradients in the lowest 3-8 mm above an irrigated green in sun, and the resulting elevation bias.
5. Can the mechanical design afford a 16-21 degree up-tilt of the cameras? If not, is manual stick-height entry acceptable for the first long putt of a round?
6. Is automatic distance needed at 3% accuracy for any reason other than the aim line (for example a displayed distance or pace advice)? If not, the 10% tolerance stands.
7. Exact current Par Aide and Standard Golf flagstick lengths, diameters, tapers, colours and stripe patterns, and how much of the nominal length sits in the cup.
8. Achievable disparity noise on the flagstick with the actual colour sensor at 3-15 m.
9. Relative yaw, roll and boresight stability of two camera cubes on one board over temperature and under one-sided sun.
10. What fraction of golfers leave the flagstick in while reading a putt, and is a "flagstick in" rule acceptable to users?
11. Should the device offer a no-camera read (user points the marker at the hole and enters paces)? Bearing error from hand pointing is the concern; it has not been measured.
12. Text of the Rules of Golf hole definition, the Equipment Rules flagstick section, and Rule 4.3, for the product documentation.

## 9. Sources

### 9.1 Pages this review tried to open (all failed; nothing was read)

The URL paths below were entered from memory and could not be confirmed to exist, because the hosts did not resolve.

1. https://www.usga.org/content/usga/home-page/rules/rules-2019/rules-of-golf/definitions.html (host not resolvable from this session)
2. https://www.randa.org/en/rog/the-rules-of-golf/rule-4 (host not resolvable from this session)
3. https://www.paraide.com/products/flagsticks (host not resolvable from this session)

### 9.2 Local material used in this review (no network)

4. The first report (JSON supplied with the task) and its calculation script, `calc.py`, in the session scratchpad.
5. `greenline-marker/docs/research/micro-cameras.md` (camera focal lengths and package sizes; UNVERIFIED there).
6. `greenline-marker/docs/research/inertial-sensors.md` (tilt accuracy, seating estimate, thermal bow).
7. `greenline-marker/docs/research/processor-radio.md` (frame memory, processor clock, capture interface).
8. `greenline-marker/docs/research/rules-compliance.md` (Rule 4.3 and alignment-device status; UNVERIFIED there).
9. `greenline-marker/sim/greenline_sim/physics.py` (putt model; functions `stimp_to_decel`, `planar_break_angle`, `planar_break_angle_paced`).
10. Recomputation scripts written for this review: `grazing_verify/verify.py` and `grazing_verify/verify2.py` in the session scratchpad.

### 9.3 References named by the first report or recalled by the reviewer (NOT opened by either pass; no URL was available; listed so a follow-up pass can find them)

11. Rules of Golf (USGA and The R&A), definition of "Hole"; Rule 4.3; Rule 13.2a.
12. Equipment Rules (USGA and The R&A), flagstick section (cited by the first report as Part 8).
13. Committee Procedures (USGA and The R&A), recommended flagstick height.
14. Par Aide Products Co. and Standard Golf Company flagstick catalogues.
15. USGA Green Section Record: Lemons, "Putting Green Speeds, Slopes, and Non-Conforming Hole Locations", 2008.
16. Federal Geodetic Control Subcommittee levelling specifications (minimum ground clearance of the line of sight).
17. Kukkamaki levelling refraction model; Holdahl 1981, NOAA Technical Memorandum NOS NGS 31.
18. Hirt, Guillaume, Wisbar, Buerki and Sternberg 2010, Journal of Geophysical Research, refraction coefficient in the lower atmosphere.
19. Penner 2002, "The physics of putting", Canadian Journal of Physics; Holmes 1991, American Journal of Physics (ball capture by the hole).
20. Andrews and Phillips, "Laser Beam Propagation through Random Media" (angle-of-arrival variance).
21. Steger 1998, IEEE PAMI (unbiased line detection); Trujillo-Pino et al. 2013 (partial-area-effect edges); Shimizu and Okutomi 2005, IJCV (pixel-locking in sub-pixel matching).
22. Dang, Hoffmann and Stiller 2009, IEEE TIP; Hansen et al. 2012, CVPR; Ling and Shen 2016, IROS; Warren, McKinnon and Upcroft 2013, ICRA (stereo self-calibration).
23. Handel 2007-2008; Podbreznik and Potocnik 2012 (camera warm-up and temperature drift).
24. MLPerf Tiny benchmark results; Lin et al., MCUNet and MCUNetV2 (microcontroller inference timings).
