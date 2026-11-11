"""The :class:`Measurements` record: everything the estimator may see.

This module deliberately imports nothing from the truth side of the
simulation (no greens, no sensor models).  :mod:`greenline_sim.estimator`
depends on this module and on the physics solver only, which is what keeps
the firmware reference free of truth leakage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["Measurements"]


@dataclass(frozen=True)
class Measurements:
    """One placement of the marker, exactly as the firmware receives it.

    Device frame: ``+x`` out of the visor, ``+y`` left, angles CCW from ``+x``.

    Attributes
    ----------
    f_px : float [px];  baseline : float [m];  h_cam : float [m]
        Calibration constants of the device that took the reading (nominal
        optical-axis height above the base plane; the true height above the
        turf is lower by the unknown sink).
    tilt : (2,) array [m/m]
        Measured surface gradient ``(dz/dx, dz/dy)`` in the device frame.
    tilt_reads : int
        1 = single placement; 2 = spin-and-reread (two seatings averaged,
        device bias cancelled).
    flag_found : bool
        Whether the flagstick was detected.  If False all ``flag_*`` values
        are NaN / False.
    flag_bearing : float [rad]
        Bearing of the flagstick in the device frame (+ = left of the visor
        axis).
    flag_disparity : float [px]
        Stereo disparity of the flagstick (``f_px * baseline / range``).
    flag_low_elev : float [rad]
        Elevation of the lowest visible point of the flagstick.
    flag_base_visible : bool
        True if that point is the base of the stick at the hole lip; False if
        the stick emerges from behind a crest of the green.
    flag_top_visible : bool
        True if the top of the stick is inside the upward field.
    flag_top_elev : float [rad]
        Elevation of the top of the stick (NaN if outside the field).
    stick_height_est : float [m];  stick_height_rel_sigma : float [relative]
        The device's knowledge of the visible stick height (learned per
        course, or the default prior) and its 1-sigma relative uncertainty.
    horizon_az : (n,) array [rad]
        Device-frame azimuths of the turf-horizon samples (empty if no
        horizon was captured).
    horizon_elev : (n,) array [rad]
        Elevation of the turf silhouette at those azimuths (NaN = invalid).
    grain_kappa : float;  grain_azimuth : float [rad]
        Measured grain strength and the direction it pushes the ball (device
        frame).
    stimp_ft : float [ft]
        Green speed entered by the golfer.
    user_distance : float [m]
        Distance dialled in by the golfer (flag-out fallback); NaN otherwise.
    """

    f_px: float
    baseline: float
    h_cam: float
    tilt: np.ndarray
    tilt_reads: int
    flag_found: bool
    flag_bearing: float
    flag_disparity: float
    flag_low_elev: float
    flag_base_visible: bool
    flag_top_visible: bool
    flag_top_elev: float
    stick_height_est: float
    stick_height_rel_sigma: float
    horizon_az: np.ndarray
    horizon_elev: np.ndarray
    grain_kappa: float
    grain_azimuth: float
    stimp_ft: float
    user_distance: float = math.nan

    def to_dict(self) -> dict:
        """Plain-JSON form (floats, bools, lists; NaN becomes ``None``)."""

        def num(v):
            v = float(v)
            return v if math.isfinite(v) else None

        return {
            "f_px": num(self.f_px),
            "baseline": num(self.baseline),
            "h_cam": num(self.h_cam),
            "tilt": [num(v) for v in self.tilt],
            "tilt_reads": int(self.tilt_reads),
            "flag_found": bool(self.flag_found),
            "flag_bearing": num(self.flag_bearing),
            "flag_disparity": num(self.flag_disparity),
            "flag_low_elev": num(self.flag_low_elev),
            "flag_base_visible": bool(self.flag_base_visible),
            "flag_top_visible": bool(self.flag_top_visible),
            "flag_top_elev": num(self.flag_top_elev),
            "stick_height_est": num(self.stick_height_est),
            "stick_height_rel_sigma": num(self.stick_height_rel_sigma),
            "horizon_az": [num(v) for v in self.horizon_az],
            "horizon_elev": [num(v) for v in self.horizon_elev],
            "grain_kappa": num(self.grain_kappa),
            "grain_azimuth": num(self.grain_azimuth),
            "stimp_ft": num(self.stimp_ft),
            "user_distance": num(self.user_distance),
        }

    @staticmethod
    def from_dict(data: dict) -> "Measurements":
        """Inverse of :meth:`to_dict` (``None`` becomes NaN)."""

        def num(v):
            return math.nan if v is None else float(v)

        return Measurements(
            f_px=num(data["f_px"]),
            baseline=num(data["baseline"]),
            h_cam=num(data["h_cam"]),
            tilt=np.array([num(v) for v in data["tilt"]], dtype=float),
            tilt_reads=int(data["tilt_reads"]),
            flag_found=bool(data["flag_found"]),
            flag_bearing=num(data["flag_bearing"]),
            flag_disparity=num(data["flag_disparity"]),
            flag_low_elev=num(data["flag_low_elev"]),
            flag_base_visible=bool(data["flag_base_visible"]),
            flag_top_visible=bool(data["flag_top_visible"]),
            flag_top_elev=num(data["flag_top_elev"]),
            stick_height_est=num(data["stick_height_est"]),
            stick_height_rel_sigma=num(data["stick_height_rel_sigma"]),
            horizon_az=np.array([num(v) for v in data["horizon_az"]], dtype=float),
            horizon_elev=np.array([num(v) for v in data["horizon_elev"]], dtype=float),
            grain_kappa=num(data["grain_kappa"]),
            grain_azimuth=num(data["grain_azimuth"]),
            stimp_ft=num(data["stimp_ft"]),
            user_distance=num(data["user_distance"]),
        )
