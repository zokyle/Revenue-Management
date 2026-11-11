"""The pure-Python kernels (no numba) are the same algorithm as the compiled ones."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from greenline_sim import physics as ph

SIM_DIR = Path(__file__).resolve().parents[1]

_SCRIPT = r"""
import json
import numpy as np
from greenline_sim import physics as ph
assert not ph.HAVE_NUMBA, ph.NUMBA_STATUS
a_r = ph.stimp_to_decel(10.0)
quad = ph.QuadraticSurface(0.012, 0.02, 0.004, -0.003, 0.005)
grid = ph.GridSurface.from_function(quad.z, (-4.0, 10.0), (-5.0, 5.0), 0.5)
grain = ph.Grain(0.08, 1.0)
out = {}
for name, surf in (("quad", quad), ("grid", grid)):
    r = ph.simulate_putt(surf, (0, 0), (5, 0), 0.10, 2.8, a_r, grain)
    s = ph.solve_aim(surf, (0, 0), (5, 0), a_r, grain, 0.30)
    b = ph.roll_batch(surf, (0, 0), (5, 0), np.array([s.phi, 0.0]), np.array([s.v0, 2.0]), a_r, grain)
    out[name] = dict(
        stop=r.stop_xy.tolist(), delta=r.delta, lateral=r.lateral_at_line, n=len(r.t), status=int(r.status),
        phi=s.phi, v0=s.v0, solve_status=int(s.status), n_rolls=s.n_rolls,
        batch_captured=b.captured.tolist(), batch_delta=b.delta.tolist(),
    )
q = ph.solve_aim_quadratic_batch(np.array([[0.01, 0.015, 0.002, 0.0, -0.001]]), 4.0, a_r)
out["qbatch"] = dict(phi=float(q.phi[0]), v0=float(q.v0[0]), status=int(q.status[0]))
print(json.dumps(out))
"""


def _reference():
    a_r = ph.stimp_to_decel(10.0)
    quad = ph.QuadraticSurface(0.012, 0.02, 0.004, -0.003, 0.005)
    grid = ph.GridSurface.from_function(quad.z, (-4.0, 10.0), (-5.0, 5.0), 0.5)
    grain = ph.Grain(0.08, 1.0)
    out = {}
    for name, surf in (("quad", quad), ("grid", grid)):
        r = ph.simulate_putt(surf, (0, 0), (5, 0), 0.10, 2.8, a_r, grain)
        s = ph.solve_aim(surf, (0, 0), (5, 0), a_r, grain, 0.30)
        b = ph.roll_batch(surf, (0, 0), (5, 0), np.array([s.phi, 0.0]), np.array([s.v0, 2.0]), a_r, grain)
        out[name] = dict(
            stop=r.stop_xy.tolist(), delta=r.delta, lateral=r.lateral_at_line, n=len(r.t), status=int(r.status),
            phi=s.phi, v0=s.v0, solve_status=int(s.status), n_rolls=s.n_rolls,
            batch_captured=b.captured.tolist(), batch_delta=b.delta.tolist(),
        )
    q = ph.solve_aim_quadratic_batch(np.array([[0.01, 0.015, 0.002, 0.0, -0.001]]), 4.0, a_r)
    out["qbatch"] = dict(phi=float(q.phi[0]), v0=float(q.v0[0]), status=int(q.status[0]))
    return out


@pytest.mark.skipif(not ph.HAVE_NUMBA, reason="already running the pure-Python kernels")
def test_pure_python_kernels_match_numba_kernels():
    env = dict(os.environ)
    env["GREENLINE_SIM_NO_NUMBA"] = "1"
    env["PYTHONPATH"] = str(SIM_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=SIM_DIR, env=env, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    pure = json.loads(proc.stdout.strip().splitlines()[-1])
    fast = _reference()
    for name in ("quad", "grid"):
        p, f = pure[name], fast[name]
        assert p["n"] == f["n"] and p["status"] == f["status"]
        assert p["solve_status"] == f["solve_status"] == int(ph.SolveStatus.OK)
        assert p["n_rolls"] == f["n_rolls"]
        assert p["batch_captured"] == f["batch_captured"] == [True, False]
        # identical algorithm; allow only last-bit differences (fused multiply-adds)
        assert np.allclose(p["stop"], f["stop"], rtol=0, atol=1e-10)
        assert p["delta"] == pytest.approx(f["delta"], abs=1e-10)
        assert p["lateral"] == pytest.approx(f["lateral"], abs=1e-10)
        assert p["phi"] == pytest.approx(f["phi"], abs=1e-9)
        assert p["v0"] == pytest.approx(f["v0"], abs=1e-9)
        assert np.allclose(p["batch_delta"], f["batch_delta"], rtol=0, atol=1e-9)
    assert pure["qbatch"]["status"] == fast["qbatch"]["status"] == int(ph.SolveStatus.OK)
    assert pure["qbatch"]["phi"] == pytest.approx(fast["qbatch"]["phi"], abs=1e-9)
    assert pure["qbatch"]["v0"] == pytest.approx(fast["qbatch"]["v0"], abs=1e-9)


def test_jit_shim_reports_its_state():
    from greenline_sim import _jit

    assert isinstance(_jit.HAVE_NUMBA, bool) and isinstance(_jit.NUMBA_STATUS, str)
    assert ph.HAVE_NUMBA == _jit.HAVE_NUMBA
    assert ph.NUMBA_STATUS == _jit.NUMBA_STATUS
    if _jit.HAVE_NUMBA:
        assert _jit.NUMBA_STATUS.startswith("numba ")
    else:
        assert _jit.prange is range
