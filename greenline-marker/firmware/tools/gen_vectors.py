#!/usr/bin/env python3
"""Generate tests/solver/gl_solver_vectors.c from the reference vectors.

Usage:
    gen_vectors.py [--check] <reference_vectors.json> <output gl_solver_vectors.c>

The input is sim/results/reference_vectors.json, written by the Python
reference (`python -m greenline_sim.refvectors`): estimator cases, solver
cases and, in its appended groups, the fallback / status cases and single
rolls.  The output is plain C data in DOUBLE precision for the host tests
(tests/test_solver.c); it is never compiled for the target.  The structures
it fills are declared by hand in tests/solver/gl_solver_vectors.h.

With --check nothing is written; the exit status is 1 if the existing file
differs from what would be generated (stale file), 0 otherwise.

JSON `null` (not a number / not available) becomes GL_VEC_NAN.  Numbers are
written with repr(), i.e. with the shortest text that reads back as the
same double.
"""
import hashlib
import json
import sys

SCHEMA_VERSION = 2
# gl_solver_method_t
METHODS = {"B1": 0, "B0": 1, "B2": 2, "STRAIGHT": 3}
MAX_HORIZON = 41
MAX_DROPS = 4


def num(value):
    """A JSON number or null as a C double expression."""
    if value is None:
        return "GL_VEC_NAN"
    text = repr(float(value))
    if text in ("nan", "inf", "-inf"):
        raise SystemExit("gen_vectors: the JSON holds a non-finite number")
    if "." not in text and "e" not in text and "E" not in text:
        text += ".0"
    return text


def nums(values, n=None):
    values = list(values)
    if n is not None and len(values) != n:
        raise SystemExit(f"gen_vectors: expected {n} numbers, got {len(values)}")
    return "{ " + ", ".join(num(v) for v in values) + " }"


def cstr(text):
    out = []
    for ch in text:
        if ch in '\\"':
            out.append("\\" + ch)
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            raise SystemExit(f"gen_vectors: non-ASCII or control character in a string: {text!r}")
    return '"' + "".join(out) + '"'


def flag(value):
    return "1" if value else "0"


def generate(data, digest):
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"gen_vectors: schema_version {data.get('schema_version')} is not {SCHEMA_VERSION}")
    for key in ("estimator_cases", "solver_cases", "fallback_estimator_cases", "fallback_solver_cases", "roll_cases"):
        if key not in data:
            raise SystemExit(f"gen_vectors: the JSON has no '{key}' (regenerate it with greenline_sim.refvectors)")
    cfg = data["estimator_config"]
    tol = data["solver_tolerances"]

    meas_rows, az_all, el_all = [], [], []
    est_rows = []

    def add_estimator(case, group):
        over = case["config_overrides"]
        unknown = set(over) - {"use_grain", "past", "lm_max_iter"}
        if unknown:
            raise SystemExit(f"gen_vectors: config override not supported by the C tests: {sorted(unknown)}")
        c = dict(cfg)
        c.update(over)
        drops = case["measurements"]
        if not 1 <= len(drops) <= MAX_DROPS:
            raise SystemExit("gen_vectors: a case has no drop or more than GL_SOLVER_MAX_DROPS")
        first = len(meas_rows)
        for m in drops:
            n_h = len(m["horizon_az"])
            if n_h != len(m["horizon_elev"]) or n_h > MAX_HORIZON:
                raise SystemExit("gen_vectors: bad horizon arrays")
            meas_rows.append(
                "    { "
                f".f_px = {num(m['f_px'])}, .baseline = {num(m['baseline'])}, .h_cam = {num(m['h_cam'])}, "
                f".tilt = {nums(m['tilt'], 2)},\n      "
                f".tilt_reads = {int(m['tilt_reads'])}, .flag_found = {flag(m['flag_found'])}, "
                f".flag_base_visible = {flag(m['flag_base_visible'])}, .flag_top_visible = {flag(m['flag_top_visible'])},\n      "
                f".flag_bearing = {num(m['flag_bearing'])}, .flag_disparity = {num(m['flag_disparity'])}, "
                f".flag_low_elev = {num(m['flag_low_elev'])}, .flag_top_elev = {num(m['flag_top_elev'])},\n      "
                f".stick_height_est = {num(m['stick_height_est'])}, "
                f".stick_height_rel_sigma = {num(m['stick_height_rel_sigma'])}, "
                f".n_horizon = {n_h}, .horizon_first = {len(az_all)},\n      "
                f".grain_kappa = {num(m['grain_kappa'])}, .grain_azimuth = {num(m['grain_azimuth'])}, "
                f".stimp_ft = {num(m['stimp_ft'])}, .user_distance = {num(m['user_distance'])} }},"
            )
            az_all.extend(m["horizon_az"])
            el_all.extend(m["horizon_elev"])
        e = case["expected"]
        stations = list(e["stations"])
        if len(stations) > MAX_DROPS:
            raise SystemExit("gen_vectors: more stations than drops")
        tag = case.get("tag", "")
        est_rows.append(
            "    { "
            f".id = {int(case['id'])}, .group = {group}, .mode = {cstr(case['mode'])},\n      .tag = {cstr(tag)},\n      "
            f".method = {METHODS[case['method']]}, .use_grain = {flag(c['use_grain'])}, .past = {num(c['past'])}, "
            f".tol_miss = {num(c['tol_miss'])}, .tol_pace = {num(c['tol_pace'])}, .lm_tol = {num(c['lm_tol'])}, "
            f".lm_max_iter = {int(c['lm_max_iter'])}, .lm_max_iter_overridden = {flag('lm_max_iter' in over)},\n      "
            f".n_drops = {len(drops)}, .first_meas = {first},\n      .exp = {{\n        "
            f".patch = {nums(e['patch'], 5)},\n        .level_offsets = {nums(e['level_offsets'], 2)}, "
            f".distance = {num(e['distance'])}, .distance_sigma = {num(e['distance_sigma'])},\n        "
            f".range_stereo = {num(e['range_stereo'])}, .range_mono = {num(e['range_mono'])}, "
            f".bearing = {num(e['bearing'])},\n        .n_stations = {len(stations)}, "
            f".stations = {nums(stations + [0.0] * (MAX_DROPS - len(stations)), MAX_DROPS)},\n        "
            f".phi = {num(e['phi'])}, .aim_azimuth_device = {num(e['aim_azimuth_device'])}, .v0 = {num(e['v0'])}, "
            f".plays_like = {num(e['plays_like'])},\n        .break_m = {num(e['break_m'])}, "
            f".break_cups = {num(e['break_cups'])}, .slope_pct = {num(e['slope_pct'])}, "
            f".fall_line_azimuth = {num(e['fall_line_azimuth'])},\n        .dz_hole = {num(e['dz_hole'])}, "
            f".cross_slope_sigma = {num(e['cross_slope_sigma'])}, .confidence = {num(e['confidence'])}, "
            f".a_r = {num(e['a_r'])},\n        .grain = {nums(e['grain'], 2)}, "
            f".tilt_slopes = {nums(e['tilt_slopes'], 2)}, .fit_cost = {num(e['fit_cost'])},\n        "
            f".base_hidden = {flag(e['base_hidden'])}, .flag_missing = {flag(e['flag_missing'])}, "
            f".range_missing = {flag(e['range_missing'])}, .poor_horizon = {flag(e['poor_horizon'])}, "
            f".used_horizon = {flag(e['used_horizon'])},\n        .fit_converged = {flag(e['fit_converged'])}, "
            f".aim_source = {int(e['aim_source'])}, .solve_status = {int(e['solve_status'])}, "
            f".fit_starts = {int(e['fit_starts'])} }} }},"
        )

    for case in data["estimator_cases"]:
        add_estimator(case, 0)
    n_est_original = len(est_rows)
    for case in data["fallback_estimator_cases"]:
        add_estimator(case, 1)

    sol_rows = []

    def add_solver(case, group):
        sol_rows.append(
            "    { "
            f".id = {int(case['id'])}, .group = {group},\n      .tag = {cstr(case['tag'])},\n      "
            f".coeffs = {nums(case['coeffs'], 5)}, .distance = {num(case['distance'])}, "
            f".stimp_ft = {num(case['stimp_ft'])}, .a_r = {num(case['a_r'])},\n      "
            f".grain = {nums(case['grain'], 2)}, .past = {num(case['past'])}, .tol_miss = {num(tol['tol_miss'])}, "
            f".tol_pace = {num(tol['tol_pace'])}, .max_rolls = {int(case.get('max_rolls', data['constants']['MAX_ROLLS']))},\n      "
            f".status = {int(case['status'])}, .compare_values = {flag(case['compare_values'])}, "
            f".phi = {num(case['phi'])}, .v0 = {num(case['v0'])}, .v_hole = {num(case['v_hole'])}, "
            f".miss = {num(case['miss'])},\n      .plays_like = {num(case['plays_like'])}, "
            f".aim_offset = {num(case['aim_offset'])}, .n_rolls = {int(case.get('n_rolls', -1))} }},"
        )

    for case in data["solver_cases"]:
        add_solver(case, 0)
    n_sol_original = len(sol_rows)
    for case in data["fallback_solver_cases"]:
        add_solver(case, 1)

    roll_rows = []
    for case in data["roll_cases"]:
        roll_rows.append(
            "    { "
            f".id = {int(case['id'])},\n      .tag = {cstr(case['tag'])},\n      "
            f".coeffs = {nums(case['coeffs'], 5)}, .z0 = {num(case['z0'])}, .start = {nums(case['start'], 2)}, "
            f".hole = {nums(case['hole'], 2)},\n      .phi = {num(case['phi'])}, .v0 = {num(case['v0'])}, "
            f".a_r = {num(case['a_r'])}, .grain = {nums(case['grain'], 2)}, "
            f".capture_exponent = {num(case['capture_exponent'])},\n      "
            f".stop_on_capture = {flag(case['stop_on_capture'])}, .status = {int(case['status'])}, "
            f".crossed = {flag(case['crossed_hole_line'])}, .captured = {flag(case['captured'])}, "
            f".side = {int(case['side'])},\n      .t_end = {num(case['t_end'])}, "
            f".stop_xy = {nums(case['stop_xy'], 2)}, .delta = {num(case['delta'])}, "
            f".speed_at_delta = {num(case['speed_at_delta'])},\n      "
            f".lateral_at_line = {num(case['lateral_at_line'])}, .speed_at_line = {num(case['speed_at_line'])}, "
            f".lateral_miss = {num(case['lateral_miss'])}, .shortfall = {num(case['shortfall'])},\n      "
            f".path_length = {num(case['path_length'])}, .n_steps = {int(case['n_steps'])} }},"
        )

    consts = data["constants"]
    out = []
    out.append("/*")
    out.append(" * gl_solver_vectors.c - GENERATED by tools/gen_vectors.py from")
    out.append(" * sim/results/reference_vectors.json.  DO NOT EDIT.  Run `make config` after")
    out.append(" * regenerating the JSON; `make test` fails if this file is stale.")
    out.append(" *")
    out.append(" * Reference vectors of the Python reference (sim/greenline_sim) as C data in")
    out.append(" * double precision, for the host tests only (tests/test_solver.c).")
    out.append(f" * Source: schema {data['schema_version']}, seed {data['seed']}, sha256 {digest}.")
    out.append(f" * {n_est_original} + {len(est_rows) - n_est_original} estimator cases, "
               f"{n_sol_original} + {len(sol_rows) - n_sol_original} solver cases, {len(roll_rows)} rolls.")
    out.append(" */")
    out.append('#include "gl_solver_vectors.h"')
    out.append("")
    out.append(f"const char gl_vec_source_sha256[] = \"{digest}\";")
    out.append(f"const double gl_vec_const_g = {num(consts['G'])};")
    out.append(f"const double gl_vec_const_hole_r = {num(consts['HOLE_R'])};")
    out.append(f"const double gl_vec_const_dt = {num(consts['DT'])};")
    out.append(f"const double gl_vec_const_t_max = {num(consts['T_MAX'])};")
    out.append(f"const unsigned gl_vec_const_step_budget_factor = {int(consts['STEP_BUDGET_FACTOR'])}u;")
    out.append(f"const unsigned gl_vec_const_max_rolls = {int(consts['MAX_ROLLS'])}u;")
    out.append("")
    out.append("/* horizon samples of all measurements, one after the other */")
    for name, values in (("gl_vec_horizon_az", az_all), ("gl_vec_horizon_elev", el_all)):
        out.append(f"const double {name}[] = {{")
        for i in range(0, len(values), 6):
            out.append("    " + ", ".join(num(v) for v in values[i : i + 6]) + ",")
        out.append("};")
    out.append(f"const unsigned gl_vec_n_horizon = {len(az_all)}u;")
    out.append("")
    out.append("const gl_vec_meas_t gl_vec_meas[] = {")
    out.extend(meas_rows)
    out.append("};")
    out.append(f"const unsigned gl_vec_n_meas = {len(meas_rows)}u;")
    out.append("")
    out.append("/* estimator_cases, then fallback_estimator_cases */")
    out.append("const gl_vec_est_case_t gl_vec_est[] = {")
    out.extend(est_rows)
    out.append("};")
    out.append(f"const unsigned gl_vec_n_est = {len(est_rows)}u;")
    out.append(f"const unsigned gl_vec_n_est_original = {n_est_original}u;")
    out.append("")
    out.append("/* solver_cases, then fallback_solver_cases */")
    out.append("const gl_vec_sol_case_t gl_vec_sol[] = {")
    out.extend(sol_rows)
    out.append("};")
    out.append(f"const unsigned gl_vec_n_sol = {len(sol_rows)}u;")
    out.append(f"const unsigned gl_vec_n_sol_original = {n_sol_original}u;")
    out.append("")
    out.append("const gl_vec_roll_case_t gl_vec_roll[] = {")
    out.extend(roll_rows)
    out.append("};")
    out.append(f"const unsigned gl_vec_n_roll = {len(roll_rows)}u;")
    return "\n".join(out) + "\n"


def main(argv):
    args = [a for a in argv[1:] if a != "--check"]
    check = "--check" in argv[1:]
    if len(args) != 2:
        print(__doc__)
        return 2
    with open(args[0], "rb") as fh:
        raw = fh.read()
    text = generate(json.loads(raw), hashlib.sha256(raw).hexdigest())
    if check:
        try:
            with open(args[1]) as fh:
                current = fh.read()
        except OSError:
            current = None
        if current != text:
            print(f"gen_vectors: {args[1]} is stale: run `make config`")
            return 1
        return 0
    with open(args[1], "w") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
