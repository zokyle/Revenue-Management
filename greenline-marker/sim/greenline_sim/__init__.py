"""GreenLine ball-marker simulation: Python reference for the firmware.

Modules
-------
physics       rolling-ball model, surfaces, putt simulation, aim solver
greens        seeded synthetic putting greens and putt scenarios (the truth)
measurements  the ``Measurements`` record - all the estimator may see
sensors       sensor forward models: true green -> ``Measurements``
estimator     the firmware reference: ``Measurements`` -> aim line, pace, break
montecarlo    Monte-Carlo evaluation (``python -m greenline_sim.montecarlo``)
report        REPORT.md and plots from the Monte-Carlo summary
refvectors    reference vectors for the C port

``estimator`` imports only ``measurements`` and ``physics``; it cannot see
the true green.

All quantities are SI (metres, seconds, radians) unless a name says otherwise
(``stimp_ft``).
"""

from . import estimator, greens, measurements, physics, sensors

__version__ = "0.2.0"

__all__ = ["physics", "greens", "measurements", "sensors", "estimator", "__version__"]
