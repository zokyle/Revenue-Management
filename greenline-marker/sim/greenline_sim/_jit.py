"""Optional numba acceleration with a pure-Python fallback.

The numerical kernels in :mod:`greenline_sim.physics` are written as plain
scalar Python (loops, floats, small arrays) so that they

* read like the C firmware they will be ported to, and
* run unchanged either under ``numba.njit`` (fast) or as ordinary Python
  (slow, but bit-for-bit the same algorithm).

Set the environment variable ``GREENLINE_SIM_NO_NUMBA=1`` before importing
the package to force the pure-Python path (used by the test-suite to prove
that both paths agree).
"""

from __future__ import annotations

import os

__all__ = ["HAVE_NUMBA", "NUMBA_STATUS", "njit", "prange"]

_ENV_FLAG = "GREENLINE_SIM_NO_NUMBA"

HAVE_NUMBA = False
NUMBA_STATUS = "not checked"

if os.environ.get(_ENV_FLAG, "0") not in ("", "0"):
    NUMBA_STATUS = f"disabled by environment variable {_ENV_FLAG}"
else:
    try:
        import numba as _numba
    except ImportError as exc:  # optional dependency: fall back, but say why
        NUMBA_STATUS = f"numba not importable ({exc}); using pure-Python kernels"
    else:
        HAVE_NUMBA = True
        NUMBA_STATUS = f"numba {_numba.__version__}"


if HAVE_NUMBA:
    njit = _numba.njit
    prange = _numba.prange
else:

    def njit(*args, **kwargs):
        """No-op stand-in for ``numba.njit`` (supports both decorator forms)."""
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]

        def _decorator(func):
            return func

        return _decorator

    prange = range
