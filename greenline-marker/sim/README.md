# GreenLine simulation (`greenline_sim`)

Python reference for the GreenLine electronic ball marker: the putt physics,
the synthetic greens it is evaluated on, the sensor models, the estimator the
firmware is ported from, and a Monte-Carlo evaluation that predicts how well
the device would read putts.

Everything is SI (metres, seconds, radians, slopes as rise/run) unless a name
says otherwise (`stimp_ft`).

## Layout

| Path | Content |
| --- | --- |
| `greenline_sim/physics.py` | rolling-ball model, surfaces, `simulate_putt`, `roll_batch`, `solve_aim` and its batch forms |
| `greenline_sim/greens.py` | seeded synthetic greens (surface, boundary, collar/rough canopy, surround terrain, speed, grain, flagstick) and putt scenarios: the TRUTH |
| `greenline_sim/measurements.py` | the `Measurements` record: everything the estimator may see (imports nothing from the truth side) |
| `greenline_sim/sensors.py` | sensor forward models: true green and marker pose -> `Measurements` (tilt, flagstick, turf horizon, grain, entered Stimp), with every noise term a named parameter of `SensorParams` |
| `greenline_sim/estimator.py` | the firmware reference: `Measurements` -> fitted patch, aim line, launch speed, plays-like distance, break, confidence. Imports only `measurements` and `physics` |
| `greenline_sim/montecarlo.py` | Monte-Carlo evaluation, `python -m greenline_sim.montecarlo` |
| `greenline_sim/report.py` | `REPORT.md` and the plots from `results/summary.json` |
| `greenline_sim/refvectors.py` | reference vectors for the C port |
| `greenline_sim/bench.py` | timing and closed-form checks (`python -m greenline_sim.bench`) |
| `greenline_sim/_jit.py` | optional numba acceleration with a pure-Python fallback |
| `tests/` | pytest suite |
| `results/` | outputs: `REPORT.md`, `summary.json`, `fig*.png`, `reference_vectors.json`, `REFERENCE_VECTORS.md` |

## Running

```
cd sim
python -m pytest -q                 # tests (about 25 s with numba)
python -m greenline_sim.montecarlo  # full evaluation: results/REPORT.md, summary.json, plots, reference vectors (about 6 min on 4 cores)
python -m greenline_sim.report      # rebuild REPORT.md and the plots from an existing summary.json
python -m greenline_sim.refvectors  # regenerate the reference vectors only
python -m greenline_sim.bench       # solver timing + closed-form table
```

`python -m greenline_sim.montecarlo --n-seeds 150 --n-seeds-sweep 60` are the
defaults (150 greens per class, i.e. 150 putts per length x class cell; the
sweeps use the first 60). The run is deterministic for a given `--seed`.

numba is used when it is importable. `GREENLINE_SIM_NO_NUMBA=1` forces the
pure-Python kernels: the same algorithm, about 50x slower for `solve_aim` on
a quadratic patch (about 20 ms per solve) and about 1000x slower for rolls on
a grid surface, so it is a correctness fallback, not a way to run the Monte
Carlo. `tests/test_fallback.py` checks that both paths give the same numbers;
the tests that run the whole Monte-Carlo pipeline are skipped without numba.

## What the device measures, and what it does not

From about 5 mm above the turf the device has: the puck's tilt (the local
slope, corrupted by how the puck seats on the grass); the flagstick's bearing,
stereo range, the elevation of its lowest visible point and, beyond about
6.7 m, of its top; the turf horizon (the silhouette of the grass at each
azimuth); a coarse grain reading; and the green speed the golfer enters. It
cannot see the surface between ball and hole in a range-resolved way: at lens
height `h` the ground at distance `d` spans only `h / d^2` rad per metre.
Nothing in `sensors.py` or `estimator.py` pretends otherwise.

## The estimator in one paragraph

In the putt frame (origin at the marker, +x toward the hole along the measured
flag bearing) the green is modelled as the quadratic patch
`z = a x + b y + 0.5 (c x^2 + 2 d x y + e y^2)`. Its coefficients are the MAP
estimate (Levenberg-Marquardt, Huber loss) from the tilt, the hole height
seen at the base of the flagstick (a one-sided bound when a crest hides the
base), optionally the turf horizon through the exact forward model of a
quadratic seen from lens height, and Gaussian priors on the curvatures. The
putt is then solved on the patch with the entered Stimp and the measured
grain. Methods: `STRAIGHT`, `B0` (tilt-only plane), `B1` (Quick Read, the
default), `B2` (B1 + horizon); a spin-and-reread measurement makes B1 the
Precision Read, and `estimate_survey` fits several drops along the line.

```python
from greenline_sim import greens as gr, sensors as se, estimator as es

sc = gr.make_scenario("gentle", 4.5, seed=7)
meas, truth = se.measure(sc.green, sc.ball_xy, sc.hole_xy, se.SensorParams(), rng=1)
est = es.estimate(meas)              # takes the Measurements only; `truth` is for evaluation
print(est.aim_azimuth_device, est.v0, est.plays_like, est.break_cups, est.slope_pct, est.confidence)
```

The headline results, the test of the turf-horizon hypothesis, the
seating-noise sensitivity and a list of what did not work as hoped are in
`results/REPORT.md`.

## Physics in one paragraph

A ball rolling on a gently sloped surface `z(x, y)` obeys
`dv/dt = -a_r v_hat - (5/7) G grad z + kappa a_r g_hat` with
`a_r = 1.83^2 / (2 * stimp_ft * 0.3048)` (Stimp 10 -> 0.549 m/s^2). Grain is
a constant push of strength `kappa` along `g_hat`. The ball rests where its
speed reaches zero and the slope-plus-grain drive does not exceed `a_r`;
otherwise it keeps rolling and the roll ends with status `MAX_TIME` or
`OUT_OF_BOUNDS`. Integration is RK4 (default `dt` = 0.02 s) with a
jitter-free stop; rest positions are converged to about 1e-8 m.

Conventions: angles CCW from +x; the aim angle `phi` is measured from the
straight ball->hole line, positive = aim left; "left/right of the hole" are
as seen from the ball.

## Minimal example

```python
from greenline_sim import physics as ph, greens as gr

sc = gr.make_scenario("undulating", 6.0, seed=3)        # green + hole + ball
g = sc.green
aim = ph.solve_aim(g.surface, sc.ball_xy, sc.hole_xy, g.a_r, g.grain, past=0.30)
print(aim.status.name, aim.phi, aim.v0, aim.aim_offset, aim.plays_like)

putt = ph.simulate_putt(g.surface, sc.ball_xy, sc.hole_xy, aim.phi, aim.v0, g.a_r, g.grain)
print(putt.captured, putt.delta, putt.lateral_at_line, putt.stop_xy)

# estimator-style: a quadratic patch in the putt frame (ball at origin, hole at (D, 0))
patch = ph.QuadraticSurface(a=0.004, b=0.012, c=0.001, d=0.0, e=-0.002)
aim2 = ph.solve_aim(patch, (0.0, 0.0), (sc.distance, 0.0), g.a_r, g.grain.rotated(sc.bearing))

# what a grazing camera sees beyond the putting surface, and the optimistic twin
print(g.canopy_z(0.0, 20.0), g.without_fringe().canopy_z(0.0, 20.0))
```

## Things worth knowing

* `solve_aim` returns an `AimSolution` with an explicit `status`. Only
  `SolveStatus.OK` means "passes through the hole centre at the target pace".
  `PACE_LIMITED` means the line through the hole exists but the ball cannot
  arrive as slowly as asked (steep downhill, or `past = 0` on a slope where
  the dying ball would have to curl back to the hole). The other statuses
  mean no usable line was found; the best iterate is still returned, with
  its residual `miss`. Failures occur where the slope-plus-grain drive near
  the path approaches or exceeds `a_r`.
* The capture rule (Holmes 1991 / Penner 2002: holed if the impact parameter
  is below the hole radius and the speed there is below
  `1.63 * sqrt(1 - (delta/R)^2)` m/s) is an assumption and can be swapped:
  `CaptureModel(exponent=1.0)` or any `callable(delta, speed) -> bool`.
* `GridSurface` needs a uniform grid; it is a C2 bicubic B-spline through the
  samples with an exact analytic gradient.
* A `Green` keeps three heights apart: `z` (what the ball rolls on: the
  putting surface and its smooth continuation), `terrain_z` (the true ground:
  `z` plus the surround terrain beyond the collar) and `canopy_z` (what a
  grazing camera sees: `terrain_z` plus the +8 mm collar / +40 mm rough
  canopy). On the putting surface all three coincide.
  `Green.without_fringe()` is the optimistic twin with neither canopy steps
  nor surround terrain and the very same rolling surface.
* The surround terrain (mean radial slope -8 % ... +2 % with azimuthal
  variation) is an assumption with named parameters in `GreenParams`, not
  survey data.

## Measured (4 cores, numba 0.68)

* `solve_aim`, one call at a time, random quadratic patches (slope <= 3 %,
  curvature sigma 0.002 1/m, 1-12 m, Stimp 8-13, grain <= 0.15): mean 0.4 ms,
  median 0.25 ms, 99th percentile 1.5 ms; 99.6 % solve. The rare failing
  solve uses its whole budget of 200 trial rolls (about 25 ms).
* `solve_aim_quadratic_batch`: about 0.05 ms per solve wall clock.
* `roll_batch`: about 10 microseconds per putt wall clock.
* Dying putt on a pure cross slope: solved `phi` over `(5/14) G s / a_r` is
  1.0008 (0.5 %, Stimp 8) to 1.031 (2 %, Stimp 12.5), the same at 2, 4 and
  8 m to 3e-5; the excess is the neglected second-order term.
* 10 ft, 1 % cross slope, Stimp 10, 0.43 m past: aim offset 0.137 m.

## Status

All modules are complete and tested (`python -m pytest -q`). The numbers in
`results/` were produced by `python -m greenline_sim.montecarlo` with the
default seed.
