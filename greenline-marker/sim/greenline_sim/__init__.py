"""GreenLine ball-marker simulation: Python reference for the firmware.

Modules
-------
physics   rolling-ball model, surfaces, putt simulation, aim solver
greens    seeded synthetic putting greens and putt scenarios

(The sensor forward models, estimator and Monte-Carlo evaluation live in
``sensors``, ``estimator`` and ``montecarlo``.)

All quantities are SI (metres, seconds, radians) unless a name says otherwise
(``stimp_ft``).
"""

from . import greens, physics

__version__ = "0.1.0"

__all__ = ["physics", "greens", "__version__"]
