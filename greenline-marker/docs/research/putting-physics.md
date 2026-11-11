# GreenLine research: Putting physics, break models, green speed, hole capture, human/product baselines, and the firmware + Monte-Carlo model for the GreenLine electronic ball marker

Date: 2026-11-11

Status: FIRST-PASS research report. The independent verification pass for this topic was cut off by a machine restart, so nothing here has had a second check. Treat every sourced number as UNVERIFIED until re-checked; the physics that matters to the design is re-derived and tested numerically in `sim/` (see `sim/results/REPORT.md`).

## Summary

The preliminary small-slope result is CONFIRMED: for a putt that dies at the hole on a plane with cross-slope s, the aim angle is alpha = (5/14)*g*s/a, independent of distance (my derivation, checked by numeric integration to +0.3..2% for s <= 2%; it under-predicts by 5% at 3%/Stimp 10 and 8-17% at 3-4%/Stimp 13, where a numeric solve is needed). With a = 6.00 ft/s squared / (2*Stimp) = 5.486/S_ft m/s^2 this is alpha = s/(2*rho_g), rho_g = 0.7833/S_ft, i.e. 64 mrad (3.7 deg) per 1% slope at Stimp 10. Three extensions matter for the device: (1) along-line slope: alpha = (5/14) g s_perp / (a + (5/7) g s_par); (2) realistic pace (ball would roll p past): multiply by k = 1 - (p/D) ln(1 + D/p) (0.65 at 5 ft, 0.76 at 10 ft, 0.85 at 20 ft for p = 0.30 m), which reproduces the caddie/AimPoint rule 'inches of break = slope% x feet x Stimp / 20' within about 25%; (3) on a non-planar green the aim depends on the cross-slope averaged along the WHOLE ball-to-hole path with nearly uniform weight r/(r+p), so the marker's own tilt (a sample of the first few cm) is not sufficient and the far-field measurement is the part that carries the value. Hole capture: Holmes limit 1.63 m/s for a centred ball, falling with offset (parabolic fit attributed to Penner); at 12-17 in past the effective half-width is 41-44 mm, giving a total angular window of only +/-0.82 deg at 10 ft and +/-0.41 deg at 20 ft. My Monte-Carlo (planar 1-3% slopes, Stimp 10 and 12) says the device needs path-averaged slope error <= 0.1% (1 mrad, 0.06 deg) 1-sigma to be invisible to a tour-quality stroke and <= 0.2-0.3% for a mid-handicap stroke; Stimp must be known to about +/-0.5-1 ft; range error up to 20% barely moves the aim line. So the 0.2-0.5 mrad accelerometer target is adequate and is not the bottleneck: the bottlenecks are slope representativeness, puck seating on turf, unknown green speed, and a +/-5% model gain (skid, speed-dependent friction). Grain has little quantitative support (a USGA agronomist calls its effect on ball roll minimal), so the grain sensor is the lowest-value subsystem. Existing electronic markers are thicker and camera-less (iBreak 43 x 10 mm with 1.3 in TFT; Slopegraide 44.5 x 12.7 mm, phone-tethered; BreakMaster claims 0.1 deg). Using any slope-gauging device during a round breaches Rule 4.3a(1), so GreenLine is a practice/casual-play product. Research limits: WebFetch was blocked for every host tried (arxiv.org, en.wikipedia.org, www.physics.sydney.edu.au, www.paulhurrion.com are outside the session's allowed network domains) and the shared WebSearch budget ran out after my 35 searches, so the original Penner/Holmes equations, amateur putt-length distribution, and StrackaLine/GolfLogix/Tour Read details are unverified.

## Recommendation

Implement the model below in firmware and in the Monte-Carlo, and treat the slope measurement as a path-average problem rather than an accelerometer-precision problem.

CONSTANTS (SI)
- g = 9.80665 m/s^2; rolling-sphere factor c = 5/7.
- Ball radius R = 0.021335 m (1.680 in diameter); hole radius R_h = 0.053975 m (4.25 in diameter). Standard values, from memory.
- Stimpmeter release speed v_s = 1.8288 m/s (6.00 ft/s).
- Capture speed V_c0 = 2 R_h sqrt(g/(2R)) = 1.636 m/s.

INPUTS
- Stimp S_ft: user-entered, default 10, range 6-14, 0.5 ft steps.
- Roll-past p: default 0.30 m; options 0.23 m (9 in), 0.30 m, 0.43 m (17 in).
- Distance D (m) and bearing to the flagstick.
- s_par (rise/run toward the hole, + uphill) and s_perp (+ on the high side), each averaged along the ball-to-hole line with weight w(r) = r/(r+p).

EQUATIONS
1. a = v_s^2 / (2 x 0.3048 x S_ft) = 5.486/S_ft m/s^2; rho_g = a/(c g) = 0.7833/S_ft; mu_R = a/g.
2. Motion (pure rolling): dv/dt = -c g grad(h) - a v_hat. Ball rests when speed reaches zero and c g |grad h| < a.
3. a_par = a + c g s_par; beta = a/a_par.
4. Rolling launch speed v0 = sqrt(2 a_par (D + p)); arrival speed v_h = sqrt(2 a_par p). Plays-like distance = (D + p) a_par/a - p. Effective Stimp on the line = S/(1 + s_par/rho_g).
5. Aim angle toward the high side: dying putt alpha0 = c g s_perp/(2 a_par) = s_perp/(2(rho_g + s_par)). With pace and s_par = 0: alpha = alpha0 [1 - (p/D) ln(1 + D/p)]. General: xi = sqrt(p/(D+p)); alpha = (c g s_perp/a_par) (1/(1-beta)) [1 - (1+beta)(1-xi^2)/(2(1-xi^(1+beta)))].
6. Displayed line bearing = flag bearing + K_b x alpha. K_b is an empirical gain, default 1.00, calibratable 0.90-1.10, absorbing skid, speed-dependent friction and grain.
7. Capture: holed if delta < R_h and v_h < V_c0 [1 - (delta/R_h)^2]; delta_max = R_h sqrt(1 - v_h/V_c0).
8. Validity: if S_ft x slope% > 25 or alpha > 0.15 rad, solve numerically (RK2, dt 1-2 ms, backward from the hole). If S_ft x slope% > 39 or c g |s| >= a, flag 'ball may not stop'.

MONTE-CARLO DEFAULTS (assumptions unless noted)
- Stimp 10 +/- 1.5 (truncated 7-13.5); slope magnitude uniform 0.5-3%, random direction; putt lengths 5/10/15/20/30 ft or the log-normal mixture (median 18 ft).
- Stroke: tour-like direction 1.0 deg, speed 3%; mid-handicap 2.0 deg, 6%. Calibrate these against the Tour make rates (77-81% at 5 ft, 40% at 10 ft, 15% at 20 ft) before quoting product benefit.
- Device errors to sweep: cross and along slope 0.05-1% each, Stimp 0.5-2 ft, range 5-20%.

SENSOR ACCURACY TARGETS (from the table and Monte-Carlo)
- Path-averaged cross-slope: <= 0.1% (1 mrad, 0.057 deg) 1-sigma as the goal; <= 0.2-0.3% is acceptable for mid-handicap users.
- Along-line slope: <= 0.3% (it moves the 10 ft miss by 19 mm per 0.5% on a 2% cross slope).
- Stimp: +/- 0.5-1 ft.
- Range: <= 5% for the distance readout and plays-like pace; <= 20% is enough for the aim line.
- The 0.2-0.5 mrad accelerometer target is adequate. It is 3-5x tighter than the system budget, which leaves margin for seating and representativeness.

DESIGN CONSEQUENCES
- Draw the aim as a direction (angle) on the marker, not as an offset at the hole; the angle is insensitive to range error.
- Because every part of the line counts about equally, add a multi-placement mode (ball, midpoint, near the hole) as the fallback when the cameras cannot recover the far-field tilt; this is what Slopegraide does.
- Make Stimp and pace explicit user settings; they move the answer more than any sensor error.
- Ship the grain sensor only as an experimental indicator with zero default gain, or drop it to save thickness.
- Position the product as a practice / casual-play aid; it is non-conforming under Rule 4.3a(1).

Fallback if the full model proves hard to validate on real greens: display fall-line direction, slope percent and the rule-of-thumb break (slope% x ft x Stimp / 20), which is within about 25% of the physics.

## Key findings

1. **The small-slope aim formula is confirmed: die-at-the-hole putt on a plane with cross-slope s needs aim angle alpha = (5/14)*g*s/a, independent of putt length. Equivalent forms: alpha = s/(2*rho_g) in Penner's convention (a = (5/7)*rho_g*g) and alpha = lambda/2 with Cross's lambda = (5/7)tan(theta)/mu_R.** (confidence: high)

   Evidence: My derivation: with friction opposing velocity, lateral velocity obeys du/dtau = -g' + u/tau (tau = time remaining, g' = (5/7) g s), giving u0 = -g'T/2 and alpha = g'/(2a). Numeric check (RK2, backward solve from hole), ratio numeric/closed: Stimp 8: 1.003 (1%), 1.012 (2%), 1.029 (3%), 1.053 (4%); Stimp 10: 1.004, 1.019, 1.046, 1.089; Stimp 13: 1.007, 1.034, 1.084, 1.174. 5 ft and 20 ft give identical angles (e.g. 64.11 vs 64.13 mrad at Stimp 10, 1%). Published support: Cross 2024 abstract says the displaced angle is independent of launch speed and depends on launch angle and the ratio of incline angle to rolling-friction coefficient; Grober says the surface enters through one parameter, the Stimp-grade product (Stimp 8 at 1.5% behaves like Stimp 12 at 1%). I could not open either paper's full text.

   Sources: https://iopscience.iop.org/article/10.1088/1361-6404/ad2c2d, https://arxiv.org/abs/1106.1698, https://www.researchgate.net/publication/237196126_The_physics_of_putting

2. **General planar closed forms (my derivation, numerically verified): with along-line slope s_par (+ uphill) the die-at-hole aim is alpha = (5/14) g s_perp / (a + (5/7) g s_par); with pace (ball would roll p past the hole) and s_par = 0, alpha is multiplied by k = 1 - (p/D) ln(1 + D/p).** (confidence: high)

   Evidence: Numeric vs closed, Stimp 10, 10 ft: s_par -2%/s_perp 1%: 86.16 vs 85.73 mrad; +2%/1%: 51.06 vs 50.85; +2%/2% with 17 in past: 70.94 vs 70.57. Pace factor k: 0.572 (5 ft, 17 in), 0.704 (10 ft, 17 in), 0.808 (20 ft, 17 in), 0.694/0.800/0.875 for 9 in past; numeric agreement within 0.2-2%. Downhill putts break much more: at Stimp 10, 1% cross slope, 10 ft, die-at-hole aim is 104 mrad on a 3% downhill line vs 46 mrad on a 3% uphill line.

   Sources: https://iopscience.iop.org/article/10.1088/1361-6404/ad2c2d

3. **On a non-planar green the required aim offset depends on the cross-slope averaged along the whole path, weighted r/(r+p) (r = remaining distance to the hole): uniform for a dying putt, and slightly favouring the ball end with pace. This contradicts the folklore that the last few feet dominate the read, and it means the marker's own tilt alone cannot give the line unless the green is planar.** (confidence: medium)

   Evidence: My derivation: an early deflection is small in angle but has a long lever arm, a late one is large in angle with a short arm; with constant deceleration they cancel exactly, giving offset = (1/(2a)) * integral of g'_perp dr. Numeric check, 20 ft putt, Stimp 10, 2% cross-slope present on only part of the path: first half only gives 49.1% of the full aim and last half 49.0% (p = 0); with p = 0.30 m first half 54.0%, last half 44.0%, last quarter 18.5% (predicted 55.1/44.9/19.0%). A MyGolfSpy review of level-type markers makes the practical point that such a marker gives a level reading only at a single point.

   Sources: https://mygolfspy.com/we-tried-it/amazon-finds-golf-ball-marking-level/, https://mygolfspy.com/news-opinion/this-golf-ball-marker-claims-to-read-greens-so-i-had-to-try-it/

4. **Stimpmeter constants: release speed 6.00 ft/s (1.83 m/s); constant-deceleration relation a = v0^2/(2S) = 18/S ft/s^2 = 5.486/S_ft m/s^2; Penner's rolling coefficient rho_g = 7a/(5g) = 0.7833/S_ft; mu_R = a/g = 0.5595/S_ft.** (confidence: high)

   Evidence: Sourced: ball leaves the Stimpmeter at a repeatable 6.00 ft/s (1.83 m/s) when the bar is raised to about 20 deg. Secondary reports of Penner: deceleration = (5/7)*rho*g with rho = 0.196 (Stimp 4 ft) and 0.065 (Stimp 12 ft); a patent quotes 0.065 < rho_g < 0.196, average 0.131. My arithmetic reproduces 0.196 at 4 ft and 0.0653 at 12 ft exactly; 0.131 corresponds to 6 ft, not the 8 ft a forum post states. Computed table (a in m/s^2, rho_g): Stimp 8: 0.686, 0.0979; 9: 0.610, 0.0870; 10: 0.549, 0.0783; 11: 0.499, 0.0712; 12: 0.457, 0.0653; 13: 0.422, 0.0602; 14: 0.392, 0.0559.

   Sources: https://en.wikipedia.org/wiki/Stimpmeter, https://www.physicsforums.com/threads/golf-ball-rolling-coefficient.205474/, https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10857432, https://www.researchgate.net/publication/237196126_The_physics_of_putting

5. **Uphill/downhill and the Brede correction: a_eff = a + (5/7) g s_par; effective Stimp = S/(1 + s_par/rho_g); the ball will not stop when slope >= rho_g = 78.3/S_ft percent. Brede's slope correction S = 2*S_up*S_down/(S_up + S_down) follows exactly from the constant-deceleration model.** (confidence: high)

   Evidence: Brede formula sourced; practitioners apply it when up/down readings differ by more than 18 in and only on uniform slopes. Computed: Stimp 10 plays like 13.4 ft on a 2% downhill and 8.0 ft on a 2% uphill; Stimp 12 plays like 17.3 ft at -2% and 22.2 ft at -3%. Critical slopes: 7.8% (Stimp 10), 6.5% (12), 5.6% (14). A GitHub issue gives the same physics: a 3% downhill putt rolls 4.41 m with the 5/7 factor vs 3.32 m without it.

   Sources: https://en.wikipedia.org/wiki/Stimpmeter, https://www.asianturfgrass.com/post/the-brede-equation/, https://github.com/D-sorganization/UpstreamDrift/issues/15010

6. **Deceleration is not strictly constant: it rises at low speed, by roughly 10% over a 14 ft putt, and a skid phase precedes pure rolling. Treat both as a +/-5% gain uncertainty on break rather than modelling them explicitly.** (confidence: medium)

   Evidence: A Penn State cellphone-video study says its results confirm Hubbard and Alaways (1999) that deceleration varies with rolling velocity. A putter patent reports the retarding force increases at lower speeds with about 10% variation over a 14 ft (4.3 m) putt and still models it as constant. Skid: Hurrion's target is pure roll within 10-20% of putt length; a blog cites one-seventh; pure roll starts at 5/7 of launch speed for a zero-spin launch (blog-level source). My estimate (not sourced): extra downhill drift during skid adds about (4/35)*s_perp/mu_k rad, about +6% of the 10 ft break if mu_k = 0.4; mu_k for ball on turf was not verified.

   Sources: https://www.me.psu.edu/sommer/workarea/WSCG_abstract.pdf, https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10857432, https://www.paulhurrion.com/media/entering-the-drop-zone/, https://3jack.blogspot.com/2009/02/geoff-mangum-on-skid-roll.html

7. **The physics model agrees with field rules of thumb once pace is included: 'inches of break = slope% x distance(ft) x Stimp / 20' is within about +/-25% of the physics for a putt hit 9-17 in past the hole.** (confidence: medium)

   Evidence: Rule sourced from golf-instruction pages (at Stimp 10 it reduces to half the slope percentage in inches per foot). Physics vs rule, Stimp 10, 1% cross slope, 17 in past: 2.19 vs 2.50 in at 5 ft; 5.41 vs 5.00 in at 10 ft; 12.4 vs 10.0 in at 20 ft. A quoted AimPoint-style data point, Stimp 12 / 10 ft: 'about seven inches' at 1% and 10 in at 1.5%; my model gives 6.5-7.4 in and 9.8-11.2 in (17 in and 9 in past). Break offset is linear in slope percent in both.

   Sources: https://www.cubicalgolfer.com/golf-green-speed-chart/, https://swingmangolf.com/putting-zone-basic-math/, https://forums.golfwrx.com/topic/1950547-calculating-breaks-on-putts/, https://stephenlee.info/golf/physics/2025/11/16/rederiving-aimpoint.html

8. **Hole capture: a centred ball is captured only below about 1.63 m/s (Holmes 1991); the limit falls with impact offset delta. Recommended criterion: holed if v_h < 1.636*[1 - (delta/R_h)^2] m/s, giving capture half-width delta_max = R_h*sqrt(1 - v_h/1.636).** (confidence: medium)

   Evidence: Holmes predicts 1.626 m/s for a uniform ball with no skid or bounce off the far rim; a thesis reports Penner's 1.63 m/s as valid only through the centre. V_c0 = 2*R_h*sqrt(g/(2R)) = 1.636 m/s with R_h = 53.975 mm, R = 21.335 mm (my arithmetic); the simpler (2R_h - R) variant gives 1.313 m/s, matching the 1.31 m/s figure on a Stanford course page. The parabolic and sqrt offset forms come from a GitHub issue summarising Penner, not from the paper itself. Check: at Stimp 10 and 17-18 in past, v_h = 0.69 m/s and the parabolic form gives 82 mm = 3.2 in effective width; a putting-trainer patent independently states about 3.25 in at 18 in past. Computed half-widths (Stimp 11): 47.1 mm at 6 in past, 45.4 at 9 in, 44.0 at 12 in, 41.8 at 17 in, 39.1 at 24 in, 34.8 at 36 in. Hurrion claims a harsher shrink (under one third at 18 in past) and Sheppard et al. report about 25% smaller effective hole straight uphill at 0.65 m/s. Hogan and Antali (2025) add rim and hole lip-out regimes.

   Sources: https://pubs.aip.org/aapt/ajp/article-abstract/59/2/129/1053877/Putting-How-a-golf-ball-and-hole-interact, https://stfx.scholaris.ca/server/api/core/bitstreams/6e98cc48-a9d4-43bd-a0f7-3b70d86b23ec/content, http://large.stanford.edu/courses/2007/ph210/kolkowitz2/, https://github.com/D-sorganization/AffineDrift/issues/5624, https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10201741, https://www.paulhurrion.com/wp-content/uploads/2020/07/1-An-Investigation-into-Golf-Ball-Speed-at-Hole-Entry.pdf, https://pmc.ncbi.nlm.nih.gov/articles/PMC12585879/

9. **Recommended terminal pace is not settled: Pelz 17 in past, AimPoint about 9 in, Sheppard/Hurrion test condition 0.30 m. Default the firmware to p = 0.30 m (12 in) with user options 0.23 / 0.30 / 0.43 m, because pace changes the aim angle by 15-35%.** (confidence: medium)

   Evidence: Pelz: optimum speed carries the ball 17 in past the hole regardless of putt length; the Putting Bible (p. 191, via forum quote) says 17 in is an average and downhill optimum is a little lower; critics note greens are faster now. One reference sets Pelz's 17 in against a 9 in AimPoint figure. Sheppard, Hurrion and Collinson (2016) studied putts finishing 0.30 m past. Effect on aim (Stimp 10, 1%, 10 ft): 64 mrad dying, 51 mrad at 9 in past, 45 mrad at 17 in past.

   Sources: https://thesandtrap.com/forums/topic/46450-putting-capture-speed/, https://golf.com/instruction/putting/what-constitutes-good-putt-dave-pelz-timeless-tips, https://leftsidegolf.blogspot.com/2013/08/putt-17-inches-past-hole-fact-or-fiction.html, https://www.paulhurrion.com/wp-content/uploads/2020/07/1-An-Investigation-into-Golf-Ball-Speed-at-Hole-Entry.pdf

10. **Error translation table (my computation, Stimp 10, p = 0.30 m, capture half-width 43.5 mm). Aim error scales linearly with Stimp. 0.1% slope = 1.0 mrad = 0.057 deg of tilt.** (confidence: medium)

   Evidence: Columns: D | total angular half-window | aim per 1% cross slope | miss per 0.1% cross-slope error | cross-slope error that uses 25% of the capture half-width | miss per 1 ft Stimp error on a 2% slope | miss per +10% range error on a 2% slope | miss per 0.5% along-slope error on a 2% cross slope. 5 ft | 28.5 mrad (1.64 deg) | 41.2 mrad (2.47 in at hole) | 6.3 mm | 0.17% | 12.5 mm | 3.5 mm | 8.0 mm. 10 ft | 14.3 mrad (0.82 deg) | 48.7 mrad (5.84 in) | 14.8 mm | 0.073% | 29.7 mm | 5.4 mm | 19.0 mm. 15 ft | 9.5 mrad (0.55 deg) | 52.2 mrad (9.39 in) | 23.8 mm | 0.046% | 47.7 mm | 6.6 mm | 30.4 mm. 20 ft | 7.1 mrad (0.41 deg) | 54.2 mrad (13.0 in) | 33.1 mm | 0.033% | 66.1 mm | 7.5 mm | 42.0 mm. 30 ft | 4.8 mrad (0.27 deg) | 56.6 mrad (20.4 in) | 51.8 mm | 0.021% | 103.5 mm | 8.8 mm | 65.3 mm. At Stimp 12 the miss per 0.1% slope error is 7.5 / 17.8 / 28.6 / 39.7 / 62.1 mm. Range error has almost no effect on the aim ANGLE (only through k), so the line should be displayed as a direction, not as an offset at the hole.

   Sources: none given

11. **Monte-Carlo requirement (my simulation): path-averaged slope error of 0.1% per axis (1-sigma) costs a tour-quality stroke under 1.5 points of make rate; 0.2% costs 3-4 points at 5-10 ft, 0.3% costs 8-9 points, 0.5% costs 16-18 points, 1% roughly halves it. For a mid-handicap stroke errors up to 0.2-0.3% are nearly invisible. Stimp error 0.5 ft costs 1-2 points, 1 ft about 3, 2 ft about 10. Range error up to 20% costs under 1 point.** (confidence: medium)

   Evidence: Planar greens, slopes 1/2/3% at 45/90/135 deg to the line, p = 0.30 m, capture by the parabolic criterion; golfer supplies pace. Stroke assumptions are mine, not sourced: tour-like = direction 1.0 deg, speed 3%; mid-handicap = 2.0 deg, 6%. Stimp 10, tour-like, make % at 5/10/15/20/30 ft: perfect read 87.1/50.8/32.0/22.1/13.1; sigma 0.1%: 85.7/49.4/30.4/22.1/12.4; 0.2%: 82.7/46.5/29.0/20.1/11.3; 0.3%: 79.0/41.4/25.7/17.7/9.7; 0.5%: 68.7/34.5/19.7/13.2/7.6; 1.0%: 47.6/21.1/12.0/7.8/4.2. Mid-handicap: 52.9/23.6/13.3/8.7/4.6 perfect read, 50.7/21.0/12.1/8.3/4.3 at 0.3%, 36.9/14.2/7.9/5.2/2.6 at 1%. Stimp 12, tour-like: 87.0/50.0/32.3/21.5/12.7 perfect, 75.9/38.1/24.6/16.1/8.8 at 0.3%. Perfect stroke isolates the device: at sigma 0.1% make rate is 100/99.5/93.8/83.0/63.1% (Stimp 10); at 0.2% it is 99.9/85.5/65.2/50.6/34.5%. Scripts: /tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/putt/mc.py and /tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/putt/putt_model.py.

   Sources: none given

12. **Human baseline: PGA Tour players make about 77-81% from 5 ft, 40% from 10 ft, 23% from 15 ft, 15% from 20 ft, 7% from 30 ft. That is equivalent to a total angular error (read + aim + stroke + green) of roughly 1.3-1.4 deg at 5 ft, 1.6 deg at 10 ft, 1.9 deg at 15 ft, 2.2 deg at 20 ft.** (confidence: medium)

   Evidence: golf.com (2019): 3 ft 99.4%, 4 ft 91.43%, 5 ft 80.72%, 6 ft 70.21%, 7 ft 60.6%, 11-15 ft 30.1%, 15-20 ft 18.3%, 20-25 ft 12.47%, 25+ ft 5.45%. Broadie-derived one-putt rates: 5 ft 77%, 10 ft 40%, 15 ft 23%, 20 ft 15%, 30 ft 7%, 40 ft 4%, 50 ft 3%, 60 ft 2%. Sigma equivalents are my calculation (Stimp 11, p = 12 in, Gaussian lateral error vs 44 mm half-width): 22-24 mrad at 5 ft (34-37 mm at the hole), 27.6 mrad at 10 ft (84 mm), 32.9 mrad at 15 ft, 38.2 mrad at 20 ft (233 mm). A device adding 5 mrad (0.3 deg) of read error is well inside these.

   Sources: https://golf.com/instruction/putting/pga-tour-putting-make-percentages-distance/, https://golfingfocus.com/what-percentage-of-putts-do-pros-make-tv-does-not-tell-the-story/, https://www.thediygolfer.com/blog/strokes-gained-putting, http://www.columbia.edu/~mnb2/broadie/Assets/strokes_gained_pga_broadie_20110408.pdf

13. **Golfers systematically under-read break, and green reading is the largest single contributor to putting variability among elite players, so a correct machine read has real headroom. Expect the correct line to look wrong to users.** (confidence: medium)

   Evidence: Alpenfels and Christina (about 1,300 putts): 96% of golfers under-read by more than 60%; lower handicaps read only about 8% more accurately. Golf Magazine/Pinehurst study: 65% under-read the typical putt. Pelz demonstration: actual break was three times what 120 pros estimated; his advice to amateurs is to triple the break they read. Karlsen and Nilsson (43 golfers, mean handicap 2.8, 40 putts of 2.2-19.3 m): green reading 60%, technique 34%, green inconsistency 6% (the thesis frames this for distance variability). MacKenzie and Sprigings (2005, J. Sports Sci. 23:81-87) evaluated the plumb-bob method; I could not retrieve its results.

   Sources: https://golf.com/instruction/96-percent-golfers-make-this-mistake/, https://mygolfspy.com/news-opinion/instruction/why-you-miss-breaking-putts-on-the-low-side/, https://www.golfdigest.com/story/dave-pelz-short-game-research-based-tips-golf-digest, https://www.golf.se:443/globalassets/klubb-och-anlaggning/spelarutveckling/forskning/performance-in-golf-putting_doctoral-thesis_jon-karlsen.pdf

14. **Amateur putting data: I found 3-putt and make-rate anchors but no published first-putt length distribution, so the Monte-Carlo length mixture must be an assumption.** (confidence: low)

   Evidence: Shot Scope: 83% of 3-putts start from more than 32 ft. Arccos 3-putt rates: 11.71% (6-10 handicap), 14.51% (11-15), 19.58% (15+); from 25+ ft the 11-15 bracket 3-putts 26.90% vs 19.61% for 1-5; inside 14 ft every bracket up to 20 handicap 3-putts under 10%. Broadie: 90-golfers average two putts from 19 ft. One source says 90s shooters make 66% inside 5 ft; another says a ~15 handicap makes about 50% from 4-5 ft and 15-20% from 10 ft. Proposed default mixture (my assumption, unverified): first putts log-normal with median 18 ft, truncated 2-70 ft; second putts median 3.5 ft.

   Sources: https://mygolfspy.com/study-the-anatomy-of-a-3-putt-powered-by-shot-scope/, https://mygolfspy.com/pros-vs-joes-3-putts/, http://www.columbia.edu/~mnb2/broadie/Assets/strokes_gained_pga_broadie_20110408.pdf, https://golfwrx.com/226273/are-you-wasting-your-time-on-the-putting-green/, https://scienceinsights.org/how-well-do-professional-golfers-putt-by-distance/

15. **Slopes at hole locations are about 1-3%, bounded by green speed: the 'Rule of 39' (slope% x Stimp <= 39) is the same as slope <= rho_g/2 in the physics, the point where a downhill putt rolls twice as far as on the flat. Design range: 0-4% slope, Stimp 7-14.** (confidence: medium)

   Evidence: Lemons chart (USGA Green Section Record, 2008, via Golf Digest): 2.9% 'recommended' and 3.85% highest 'marginal' at green speed 14. Golf Course Architecture: above Stimp 10, much over 2% is a sketchy hole location. USGA specialist: at 13.5 ft (U.S. Open) hole locations can be in the 3% range. Rule of 39 is from putting coach Ralph Bauer. My arithmetic: s/rho_g = slope% x Stimp / 78.3, so 39 corresponds to 0.50; a pure cross-slope putt at that limit needs about 0.25 rad (14 deg) of aim. Typical Stimp bands (public 8-9, club 10-11, Tour 12-13+) are from memory, not verified this session.

   Sources: https://www.golfdigest.com/story/2026-pga-championship-hole-locations-fair-unfair-explainer, https://golfcoursearchitecture.net/digital/magazine/issue73/40, https://www.golfcourseindustry.com/article/green-slopes-golf

16. **Rules of Golf: using a level or any device to gauge green slope during a round breaches Rule 4.3a(1), in casual rounds as well as competition. GreenLine must be positioned as a practice / training / non-conforming casual-play aid.** (confidence: high)

   Evidence: National Club Golfer: Rule 4.3a(1) prevents measuring elevation changes, using an alignment device, or using a device that gives a recommended line of play. Interpretation 4.3a(1)/1 (via Oregon Golf Association) lists using a level, a bottled drink, or a weighted string to gauge slope or contours as breaches. Penalty: general penalty for the first breach, disqualification for the second. USGA statement reported by Golf.com: Rule 4.3a always applies, casual round or not. Slopegraide's own FAQ: not legal for tournament play; usable on the practice green and in recreational rounds. Green-reading-material limits (2019) also treat producing a recommended line from the ball's position as a breach.

   Sources: https://www.nationalclubgolfer.com/rules/golf-equipment-rules-measure-slope-on-a-green/, https://archive.oga.org/node/2955, https://www.randa.org/sw/rog/clarifications/rule-4, https://slopegraide.com/pages/faqs, https://www.usga.org/content/usga/home-page/rules-hub/joint-statement-regarding-green-reading-materials.html

17. **No product found combines cameras, range to the hole, and an on-marker aim line. Existing electronic markers are 10-12.7 mm thick and measure only local tilt; GreenLine's 40-44 mm x <= 7 mm target would be 30-45% thinner than both while adding cameras.** (confidence: medium)

   Evidence: iBreak: 1.3 in colour TFT, diameter 1.7 in x height 0.4 in (43 x 10 mm), 34 g, GBP 150 listing, shows putting direction and uphill/downhill percent; no accuracy figure found. Slopegraide: 1.75 in x 0.5 in (44.5 x 12.7 mm), 30 g, Bluetooth LE 4.0, microUSB, 6-8 h battery, 60-90 min charge, no display (iPhone/iPad/Watch app), water-resistant but not for rain; its app also offers a LiDAR AR mode on iPhone/iPad Pro. Exelys BreakMaster: retailer listings claim 0.1 deg accuracy, $119.95 (list $149.95) at one US retailer. Sub-$10 bubble-level markers: MyGolfSpy found it takes a fairly extreme slope to react. PuttView X AR glasses: $14,480. StrackaLine, GolfLogix, Tour Read and PuttView Books were not retrieved (search budget exhausted).

   Sources: https://www.u-buy.co.uk/product/PNO8B15WK-ibreak-digital-golf-green-reader-informing-putting-direction-and-uphill-downhill-percent-in-real-time-titanium-silver-frame-and-1-3inch-color-tft, https://slopegraide.com/pages/faqs, https://slopegraide.com/products/slopegraide, https://oldduffergolf.com/slopegraide-course-mode/, https://www.intheholegolf.com/Breakmaster/Exelys-Breakmaster.html, https://www.amazon.com/clp/B000A0IJ08, https://mygolfspy.com/news-opinion/this-golf-ball-marker-claims-to-read-greens-so-i-had-to-try-it/, https://aceindoorgolf.com/products/puttview-x-ar-glasses

18. **Relevant prior art exists and needs a freedom-to-operate review, especially a 2026 published application describing a portable node that functions as a ball marker with terrain-compensated putting guidance.** (confidence: medium)

   Evidence: US 2026/0284501 (published 24 Sep 2026): 'System and Method for Terrain-Compensated Putting Guidance, Green-Reading Training, and Wireless Putting Distance Measurement', with a portable spatial node that functions as a ball marker; I could not read its claims. US 8,449,409 (Barkley and Pemberton, 2013): handheld green reader with non-scanning time-of-flight distance sensor, three-axis accelerometer tilt sensor, processor and colour display. WO 2013/049838 A2: smartphone camera + accelerometer + compass showing a predicted putt path. US 6,095,933 and US 5,476,258: mechanical bubble/bulls-eye level ball markers. Also seen: US 2013/0260920 (green reading method and apparatus), US 2010/0285903 (apparatus measuring Stimp), US 8,070,620 / 8,282,499 (measuring green speeds). No patent found that combines a ball marker, a camera and an accelerometer.

   Sources: https://patents.justia.com/patent/20260284501, https://patents.justia.com/patent/8449409, https://patents.google.com/patent/WO2013049838A2/en, https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/6095933, https://patents.google.com/patent/US20130260920, https://patents.justia.com/patent/20100285903

19. **Grain: I found no measured down-grain vs into-grain Stimp difference, and the most authoritative source says the effect on ball roll is minimal. The grain sensor is the weakest-justified subsystem; treat it as optional/experimental.** (confidence: low)

   Evidence: A USGA agronomist (Green Section Record, 14 Nov 2014) concluded grain has a minimal effect on ball roll on both bentgrass and bermudagrass, and that grain tends to run downhill with surface slope (so it is largely collinear with what the slope measurement already captures). Instruction sites claim grain can add or subtract 10-20% of break on bermudagrass and that it matters mostly below Stimp 10, without citing data.

   Sources: https://gsrpdf.lib.msu.edu/?file=%2Farticle%2Fwhitlark-agronomists-11-14-14.pdf, https://golfguidebook.com/stimpmeter-green-speed-explained/, https://thechiputt.com/blogs/golf-tips/how-to-read-greens-like-a-pro-complete-guide

20. **Moisture and time of day change green speed by amounts that matter to the aim (a 1 ft Stimp change moves the 10 ft aim point about 30 mm on a 2% slope), but golfers cannot perceive differences under about 6 in.** (confidence: low)

   Evidence: USGA Green Section Record: the average golfer cannot reliably detect a green-speed difference of less than 6 in on the Stimpmeter; humidity and rain affect speed and greens slow slightly through the day as they grow. A secondary site attributes to the USGA that light rain can cut Stimp by 1-1.5 ft; I could not confirm that in a USGA source.

   Sources: https://www.usga.org/content/usga/home-page/course-care/green-section-record/61/issue-08/why-do-putting-green-conditions-change-throughout-the-day-.html, https://ntro.it.com/the-science-behind-green-speed-does-water-make-greens-faster

21. **Research coverage was limited by the environment; several requested items are unverified.** (confidence: high)

   Evidence: WebFetch failed with host-not-resolved for arxiv.org, www.physics.sydney.edu.au, en.wikipedia.org and www.paulhurrion.com (these hosts would have to be allowed in the session's network settings), so no paper or page was read in full; everything sourced comes from search-result summaries. The shared WebSearch budget (200 calls per turn across all agents) was exhausted after my 35 searches; four further searches (patent 2026/0284501 details, US 8,449,409, a Golf Monthly green-reading rangefinder, GolfLogix/StrackaLine/Tour Read pricing) were refused. Not verified: Penner's and Holmes's exact equations, Lorensen and Yamrom, MacKenzie and Sprigings results, amateur putt-length distribution, typical Stimp bands.

   Sources: none given

## Products and methods reviewed

| Name | Maker | Key specs | Price | Status | Verdict | Notes |
|---|---|---|---|---|---|---|
| Closed-form planar break model (first-order, with along-slope and pace terms) | n/a (method) | alpha = (5/14) g s_perp / (a + (5/7) g s_par) for a dying putt; with pace p and s_par = 0 multiply by k = 1 - (p/D) ln(1 + D/p); general: xi = sqrt(p/(D+p)), beta = a/a_par, alpha = ((5/7) g s_perp / a_par) * (1/(1-beta)) * [1 - (1+beta)(1-xi^2)/(2(1-xi^(1+beta)))]. a = 5.486/S_ft m/s^2. Cost: a few floating-point operations. Accuracy vs numeric integration: within 2% for slope <= 2% at Stimp <= 10; -5% at 3%/Stimp 10; -8% at 3%/Stimp 13; -17% at 4%/Stimp 13. |  | n/a | recommended | My derivation, verified numerically this session; consistent with Cross 2024 (angle independent of speed, depends on slope/friction ratio) and Grober (single Stimp x grade parameter). Use path-averaged slopes with weight r/(r+p). Switch to the numeric solver when S_ft x slope% > 25 or alpha > 0.15 rad. |
| Numeric integration of the rolling-ball equation of motion, solved backward from the hole | n/a (method) | dv/dt = -(5/7) g grad(h) - a v_hat; RK2 midpoint, dt 0.5-4 ms; start at the hole with arrival speed v_h = sqrt(2 a_par p) and integrate backward until range = D, root-find arrival heading. About 0.17 s per solve in unoptimised Python; forward check lands within 0.24 mm of the hole centre. Handles non-planar surfaces and large slopes. |  | n/a | recommended | Reference implementation written this session: /tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/putt/putt_model.py (solver), /tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/putt/mc.py (vectorised Monte-Carlo), /tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/putt/tables.py (sensitivity tables), /tmp/claude-0/-home-user-Revenue-Management/8bf57d16-8cdb-5673-919d-d6fddff902fe/scratchpad/putt/weight_check.py (path-weighting check). Known edge case: the die-at-hole limit (v_h near 0) has ill-conditioned or multiple solutions on steep slopes; always solve with p > 0. |
| Holmes/Penner capture criterion, parabolic offset form | n/a (method) | Holed if delta < R_h and v_h < V_c0 * [1 - (delta/R_h)^2], V_c0 = 2 R_h sqrt(g/(2R)) = 1.636 m/s, R_h = 53.975 mm, R = 21.335 mm. Capture half-width delta_max = R_h sqrt(1 - v_h/V_c0): 54 mm dying, about 44 mm at 12 in past, 41-42 mm at 17 in past, 35 mm at 36 in past (Stimp 11). |  | n/a | recommended | 1.626-1.63 m/s is sourced (Holmes 1991 abstract, thesis citing Penner). The parabolic form is from a secondary summary of Penner, not the paper; verify before freezing. It is the conservative choice and matches an independent statement of about 3.25 in effective width at 18 in past. Does not model rim lip-outs (Hogan and Antali 2025) or uphill/downhill entry (about 25% smaller effective hole straight uphill at 0.65 m/s). |
| Free-fall chord capture criterion (sqrt form) and the 1.31 m/s simple bound | n/a (method) | v_c(delta) = 2 sqrt(R_h^2 - delta^2) sqrt(g/(2R)); half-width 50-51 mm at 12 in past, 48-49 mm at 17 in past. Simple variant with (2R_h - R) travel gives 1.313 m/s centre limit. |  | n/a | viable | Optimistic for off-centre entries because it ignores rim interaction; use only as an upper bound in sensitivity runs. |
| Rule-of-thumb break: inches = slope% x distance(ft) x Stimp / 20 | n/a (method) | Equivalent to aim angle = slope% x Stimp / 240 rad, i.e. 0.65x the die-at-hole physics; matches the physics at k of about 0.65 (5 ft at 12 in past). Versus physics at 17 in past, Stimp 10, 1%: 2.50 vs 2.19 in (5 ft), 5.00 vs 5.41 in (10 ft), 10.0 vs 12.4 in (20 ft). |  | n/a | fallback | Useful as a unit test for firmware output and as a user-facing explanation. Under-reads long putts by about 20-25%. |
| Green-speed input: user-entered Stimp with optional two-way (Brede) calibration | n/a (method) | a = 5.486/S_ft m/s^2; default S = 10 ft, range 6-14 in 0.5 ft steps; slope correction S = 2 S_up S_down/(S_up + S_down). Needed accuracy +/-0.5-1 ft (1 ft error = 12.5 / 29.7 / 66.1 mm miss at 5 / 10 / 20 ft on a 2% slope). |  | n/a | recommended | The marker cannot sense green speed from the listed sensors, so Stimp is a required user or app input. Golfers cannot perceive differences below about 6 in, so 0.5 ft steps are sufficient. |
| Grain correction term in the break model | n/a (method) | No measured coefficient found. Unsourced instruction claim: 10-20% of break on bermudagrass, mostly below Stimp 10. |  | n/a | rejected | Rejected as a default model term: no quantitative basis, and a USGA agronomist reports minimal effect on ball roll with grain generally running downhill. If the grain sensor ships, expose it as a displayed direction plus an optional user-tunable gain defaulting to zero. |
| iBreak digital golf green reader (competitor benchmark) | iBreak (maker and HQ unverified) | 1.3 in colour TFT, shows putting direction and uphill/downhill percent in real time, titanium-silver frame, 34 g. Accuracy and battery not stated in any source found. | GBP 150 on the UK listing; USD price unverified | unverified | viable | Closest form-factor benchmark: same diameter as the GreenLine target but 10 mm thick, with a display and no cameras. Local tilt only. |
| Slopegraide smart ball marker (competitor benchmark) | Jeffrey David Golf, LLC (Slopegraide) | Bluetooth LE 4.0 marker paired with iPhone/iPad/Apple Watch app that shows a recommended starting line; 30 g; battery 6-8 h (up to two rounds); 60-90 min charge via microUSB; manual on/off switch; LED indicator; case water-resistant but not recommended in rain. No accuracy specification published. App also has a LiDAR AR mode on iPhone/iPad Pro that needs no marker. | not found | active as seen | viable | Closest concept: reads slopes between ball and hole by multiple placements, no on-marker display, no cameras. Its FAQ states it is not legal for tournament play. |
| Exelys BreakMaster Digital Green Reader (competitor benchmark) | Exelys | Electronic level with LCD showing break direction and amount; retailer listings claim 0.1 deg slope accuracy (1.75 mrad = 0.175% slope); foldable, rechargeable, USB cable and case included. | 119.95 sale / 149.95 list at one US retailer | active as seen | viable | Accuracy benchmark. By my table a 0.175% slope error alone gives about 26 mm miss at 10 ft on Stimp 10 (60% of the capture half-width), so a 0.3 mrad tilt measurement would be about 5x better than this claim. Accuracy figure is retailer copy, not an independent test. |
| Bubble-level ball markers (SlopeMaster ProGreen, GreenNav Pro and similar) | various | Mechanical bubble level with directional arrows in a ball marker; under $10. | under 10 | active as seen | rejected | MyGolfSpy: showed nothing on a low-break hole and barely registered where slope was noticeable; reads a single point only. Sets the low bar GreenLine must clearly beat. |
| PuttView X AR glasses (competitor benchmark) | PuttView | HoloLens-based AR glasses that draw read, line and speed on the green; training aid. | 14,480 | active as seen | rejected | Shows the market accepts a drawn putt line as the output, at about 100x the plausible GreenLine price and in a different form factor. |

## Risks

- Rules: using the device to gauge slope or get a recommended line during a round breaches Rule 4.3a(1) (general penalty, then disqualification), and the USGA says this applies to casual rounds too. Marketing must say practice / training use.
- Representativeness: aim depends on the cross-slope averaged over the whole putt, but the accelerometer samples only the spot under the marker. On real greens slope commonly changes by 0.5% or more over 10-20 ft, which is a 16-18 point make-rate loss for a good stroke in my simulation. The value of the product rests on the far-field camera measurement or on multi-placement sampling.
- Seating error (my estimate, not sourced): on a 42 mm base, 0.042 mm of differential settlement into the turf equals 1 mrad, the whole cross-slope budget. Needs a three-point foot geometry at maximum radius, a press-and-settle routine, and measured repeatability on real turf before the tilt spec means anything.
- Green speed is unknown to the device and scales the answer linearly: a 1 ft Stimp error moves the aim point 30 mm at 10 ft and 66 mm at 20 ft on a 2% slope. Rain or dew can plausibly shift speed by a foot or more.
- Camera geometry (outside my topic but it drives feasibility): from 3-5 mm above the turf the hole itself is seen at about 1 mrad grazing angle and is effectively invisible, so the flagstick must be in the hole; a crown of only 4 mm between ball and hole hides the flagstick base; and near-ground heat shimmer could bend sight lines by the order of 0.5-2 mrad over 5 m (my physics estimate, unverified), which is the same size as the slope budget.
- Model gain uncertainty of about +/-5% of break from skid, speed-dependent friction (about 10% over a 14 ft putt) and grain; the closed form also under-predicts by 5-17% on 3-4% slopes at Stimp 10-13 unless the numeric solver is used.
- Capture model: the parabolic offset form is taken from a secondary summary of Penner and ignores lip-out dynamics and uphill/downhill entry; make-rate predictions could be off by several points.
- User behaviour: 96% of golfers under-read break by more than 60% and compensate in the stroke, so a physically correct line will look too high and may be distrusted or mis-executed. Aligning a ball to a roughly 30 mm line within 1 deg needs about 0.5 mm placement accuracy.
- Intellectual property: US 2026/0284501 (published Sep 2026) describes a ball-marker node with terrain-compensated putting guidance; US 8,449,409 and WO 2013/049838 cover distance + tilt + display and camera + accelerometer putt-path prediction. Claims were not read; a freedom-to-operate review is needed.
- Evidence quality: no full paper or product page could be opened this session and the search budget ran out, so several constants rest on search-result summaries and on my own derivations and simulation. Stroke-error parameters in the Monte-Carlo are assumptions.

## Open questions

- What are Penner's and Holmes's exact published capture equations (parabolic vs sqrt offset dependence, uphill/downhill versions)? Needs the papers: Can. J. Phys. 80:83-96 (2002) and Am. J. Phys. 59:129-136 (1991).
- What repeatability does a 40-44 mm puck actually achieve when placed on bentgrass and bermudagrass greens (tilt scatter over repeated placements, with and without three feet)? This decides whether the 1 mrad budget is reachable.
- How large is the difference between local slope at the ball and the path-averaged slope on real greens at 5, 10 and 20 ft? Needs a set of scanned green surfaces.
- Can the device estimate green speed itself, for example by having the stereo cameras time a calibration putt rolling away, or must Stimp always be entered?
- What is the real first-putt length distribution for amateurs by handicap (Arccos / Shot Scope data), to weight the Monte-Carlo?
- Is there any measured down-grain vs into-grain Stimp difference or lateral drift on bermudagrass? None was found.
- What is the kinetic friction coefficient of a golf ball skidding on a green, and how long is the skid for typical putter launch conditions, to pin down the K_b gain?
- What does US 2026/0284501 actually claim, who is the assignee, and does it read on a camera-based ball marker with an on-device aim line?
- Specifications, accuracy and prices of StrackaLine, GolfLogix, Tour Read and PuttView Books, and the BreakMaster's dimensions, were not retrieved; a follow-up search is needed.
- Which pace convention should be the product default (9 in, 12 in or 17 in past), given it changes the displayed line by 15-35%?
