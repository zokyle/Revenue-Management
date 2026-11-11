# GreenLine simulation (`greenline_sim`)

Python reference for the GreenLine electronic ball marker: the putt physics,
the synthetic greens it is evaluated on, and (in the modules listed under
"Status") the sensor models, the estimator the firmware is ported from, and a
Monte-Carlo evaluation.

Everything is SI (metres, seconds, radians, slopes as rise/run) unless a name
says otherwise (`stimp_ft`).

## Layout

| Path | Content |
| --- | --- |
| `greenline_sim/physics.py` | rolling-ball model, surfaces, `simulate_putt`, `roll_batch`, `solve_aim` and its batch forms |
| `greenline_sim/greens.py` | seeded synthetic greens (surface, boundary, collar/rough canopy, surround terrain, speed, grain, flagstick) and putt scenarios |
| `greenline_sim/bench.py` | timing and closed-form checks (`python -m greenline_sim.bench`) |
| `greenline_sim/_jit.py` | optional numba acceleration with a pure-Python fallback |
| `tests/` | pytest suite |
| `results/` | outputs of the Monte Carlo |

## Running

```
cd sim
python -m pytest -q            # tests (about 15 s with numba)
python -m greenline_sim.bench  # solver timing + closed-form table
```

numba is used when it is importable. `GREENLINE_SIM_NO_NUMBA=1` forces the
pure-Python kernels: the same algorithm, about 50x slower for `solve_aim` on
a quadratic patch (about 20 ms per solve) and about 1000x slower for rolls on
a grid surface, so it is a correctness fallback, not a way to run the Monte
Carlo. The test suite then takes about 1.5 minutes; `tests/test_fallback.py`
checks that both paths give the same numbers.

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

`physics.py` and `greens.py` are complete and tested. `sensors.py`,
`estimator.py` and `montecarlo.py` build on them.
