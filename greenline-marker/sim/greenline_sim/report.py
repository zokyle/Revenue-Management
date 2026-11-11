"""Turn the Monte-Carlo summary into ``REPORT.md`` and PNG plots.

``write_report(summary, out_dir)`` is called by
``python -m greenline_sim.montecarlo``; ``python -m greenline_sim.report``
rebuilds the report and the plots from an existing ``results/summary.json``.

Every number in the report is read from the summary dictionary; the verdict
sentences are derived from the same numbers by fixed rules (see
:func:`greenline_sim.montecarlo.verdict`), so re-running the Monte Carlo with
another seed or size regenerates a consistent report.  Where a sentence
states a direction ("ahead of", "helps", "costs") it is chosen from the
numbers by an explicit rule in this module, never typed in.
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Sequence

from . import bench
from . import physics as ph
from .montecarlo import verdict_sign

__all__ = ["write_report", "make_plots", "render", "main"]

# ---- chart style: one fixed colour per method, neutral ink for the references ----
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
METHOD_COLOR = {
    "B0": "#2a78d6",  # blue
    "B1": "#eb6834",  # orange
    "B2": "#1baf7a",  # aqua
    "B0S": "#eda100",  # yellow
    "SURVEY3": "#e87ba4",  # magenta
    "HUMAN05": "#008300",  # green
    "HUMAN10": "#6250d6",  # violet
    "SURVEY2": "#e34948",  # red
    "STRAIGHT": MUTED,
    "FLAGOUT": MUTED,
    "ORACLE": INK,
    "ORACLE_SLOPE": INK_2,
}
METHOD_MARKER = {
    "B0": "o", "B1": "s", "B2": "^", "B0S": "D", "SURVEY3": "v", "SURVEY2": "P", "HUMAN05": "X", "HUMAN10": "*",
    "STRAIGHT": "o", "FLAGOUT": "s", "ORACLE": "o", "ORACLE_SLOPE": "s",
}
METHOD_LABEL = {
    "STRAIGHT": "STRAIGHT (no read)",
    "B0": "B0 tilt only",
    "B1": "B1 Quick Read",
    "B2": "B2 + horizon (anchored)",
    "B0S": "B0S Precision Read",
    "SURVEY2": "SURVEY2",
    "SURVEY3": "SURVEY3",
    "FLAGOUT": "FLAGOUT (hand-pointed)",
    "HUMAN05": "Human, 0.5 % read",
    "HUMAN10": "Human, 1 % read",
    "ORACLE_SLOPE": "ORACLE_SLOPE (true surface, entered speed)",
    "ORACLE": "ORACLE",
}
ALL_METHODS = ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT", "HUMAN05", "HUMAN10", "ORACLE_SLOPE", "ORACLE")
HEADLINE = ("STRAIGHT", "B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE_SLOPE", "ORACLE")
SENSOR_CHAIN = ("STRAIGHT", "B0", "B1", "B2", "ORACLE")
FIT_LABEL = {
    "anchored": "anchored (B2, the estimator's default form)",
    "anchored_free_c": "anchored, c free, no silhouette offset",
    "joint": "joint fit, lowest of 25 starts",
    "joint_single_start": "joint fit, single start (the earlier implementation)",
}
FRINGE_LABEL = {
    "no_fringe": "no fringe (optimistic)",
    "no_surround": "canopy steps only",
    "realistic": "realistic as modelled",
    "mounded": "mounded surrounds (pessimistic)",
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _cm(x: Optional[float], digits: int = 1) -> str:
    return "-" if x is None else f"{100.0 * x:.{digits}f}"


def _pct(x: Optional[float], digits: int = 0) -> str:
    return "-" if x is None else f"{100.0 * x:.{digits}f}"


def _mrad(x: Optional[float], digits: int = 1) -> str:
    return "-" if x is None else f"{1000.0 * x:.{digits}f}"


def _signed(x: float, digits: int = 0) -> str:
    """Signed number without a negative zero."""
    text = f"{x:+.{digits}f}"
    return text.replace("-", "+") if float(text) == 0.0 else text


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _dkeys(summary) -> List[str]:
    return [f"{d:g}" for d in summary["meta"]["distances"]]


def _seat(summary, seat: Optional[str] = None) -> Dict[str, dict]:
    key = f"{summary['meta']['nominal_seat_mrad']:g}" if seat is None else seat
    return summary["main"]["by_seat"][key]


def _by_distance_table(tables: Dict[str, dict], methods: Sequence[str], dkeys: Sequence[str], key: str, fmt) -> str:
    rows = []
    for m in methods:
        if m in tables:
            rows.append([m] + [fmt(tables[m]["by_distance"][d].get(key)) for d in dkeys] + [fmt(tables[m]["overall"].get(key))])
    return _table(["Method"] + [f"{d} m" for d in dkeys] + ["all"], rows)


def _ci(delta: dict, key: str, scale: float, digits: int) -> str:
    return f"{scale * delta[key]:+.{digits}f} ± {1.96 * scale * delta[key + '_se']:.{digits}f}"


# --------------------------------------------------------------------------
# plots
# --------------------------------------------------------------------------


def _style(ax, xlabel: str, ylabel: str, title: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
    ax.set_xlabel(xlabel, fontsize=9, color=INK_2)
    ax.set_ylabel(ylabel, fontsize=9, color=INK_2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=3)


def _line(ax, x, y, method: str, label: Optional[str] = None, **kwargs) -> None:
    neutral = method in ("STRAIGHT", "FLAGOUT", "ORACLE", "ORACLE_SLOPE")
    ax.plot(
        x, y,
        color=METHOD_COLOR[method],
        marker=METHOD_MARKER[method],
        markersize=6.5,
        markeredgecolor=SURFACE,
        markeredgewidth=1.2,
        linewidth=1.6 if neutral else 2.0,
        linestyle=(0, (4, 2)) if method in ("STRAIGHT", "ORACLE_SLOPE") else "-",
        label=label or METHOD_LABEL[method],
        solid_capstyle="round",
        **kwargs,
    )


def _legend(ax, **kwargs) -> None:
    leg = ax.legend(fontsize=8, frameon=False, labelcolor=INK_2, **kwargs)
    return leg


def _save(fig, out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    return path


def make_plots(summary: dict, out_dir: str) -> List[str]:
    """Write the PNG figures into ``out_dir`` and return their file names."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "DejaVu Sans"
    dists = summary["meta"]["distances"]
    dkeys = _dkeys(summary)
    nominal = _seat(summary)
    names: List[str] = []

    def series(tables, method, key, scale=1.0):
        return [scale * tables[method]["by_distance"][d][key] for d in dkeys]

    # ---- 1: median lateral miss by distance ---------------------------------
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    fig.patch.set_facecolor(SURFACE)
    for m in ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05", "HUMAN10"):
        _line(ax, dists, series(nominal, m, "median_miss", 100.0), m)
    ax.axhline(100.0 * ph.HOLE_R, color=AXIS, linewidth=1.0)
    ax.annotate("hole radius 5.4 cm", (dists[-1], 100.0 * ph.HOLE_R), xytext=(0, 4), textcoords="offset points",
                ha="right", fontsize=8, color=MUTED)
    _style(ax, "putt length [m]", "median lateral miss at the hole [cm]",
           f"Lateral miss with perfect execution (seating noise {summary['meta']['nominal_seat_mrad']:g} mrad)")
    ax.set_xticks(dists)
    ax.set_ylim(0.0, None)
    _legend(ax, loc="upper left", ncol=2)
    names.append(os.path.basename(_save(fig, out_dir, "fig1_miss_by_distance.png")))
    plt.close(fig)

    # ---- 2: make probability, perfect and human execution -------------------
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.3), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, key, title in (
        (axes[0], "make_perfect", "Make probability, perfect execution"),
        (axes[1], "make_human", f"Make probability, human execution ({summary['meta']['sigma_dir_deg']:g} deg, {100 * summary['meta']['sigma_speed']:g} % speed)"),
    ):
        for m in ("STRAIGHT", "B0", "B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE_SLOPE", "ORACLE"):
            _line(ax, dists, series(nominal, m, key, 100.0), m)
        _style(ax, "putt length [m]", "putts holed [%]" if ax is axes[0] else "", title)
        ax.set_xticks(dists)
        ax.set_ylim(0.0, 104.0)
    _legend(axes[1], loc="upper right")
    names.append(os.path.basename(_save(fig, out_dir, "fig2_make_probability.png")))
    plt.close(fig)

    # ---- 3: seating-noise sensitivity ---------------------------------------
    seats = [f"{s:g}" for s in summary["meta"]["seat_levels_mrad"]]
    seat_x = [float(s) for s in seats]
    pick = [d for d in ("3", "6", "9") if d in dkeys] or dkeys[:3]
    fig, axes = plt.subplots(1, len(pick), figsize=(4.0 * len(pick), 4.2), sharey=False)
    fig.patch.set_facecolor(SURFACE)
    for ax, d in zip(list(axes) if len(pick) > 1 else [axes], pick):
        for m in ("B0", "B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10"):
            y = [100.0 * summary["main"]["by_seat"][s][m]["by_distance"][d]["median_miss"] for s in seats]
            _line(ax, seat_x, y, m)
        _style(ax, "true seating noise [mrad per axis]", "median lateral miss [cm]" if d == pick[0] else "", f"{d} m putts")
        ax.set_xticks(seat_x)
        ax.set_ylim(0.0, None)
    first_ax = axes[0] if len(pick) > 1 else axes
    handles, labels = first_ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=8.5, frameon=False, labelcolor=INK_2,
               bbox_to_anchor=(0.5, -0.07))
    names.append(os.path.basename(_save(fig, out_dir, "fig3_seating_noise.png")))
    plt.close(fig)

    # ---- 4: horizon test ------------------------------------------------------
    ht = summary["main"]["horizon_test"]
    order = [k for k in ("no_fringe", "no_surround", "realistic", "mounded") if k in ht]
    forms = [f for f in ("anchored", "joint", "joint_single_start") if f in ht[order[0]]]
    form_style = {
        "anchored": (METHOD_COLOR["B2"], "o", "anchored (B2)"),
        "joint": (METHOD_COLOR["B0"], "s", "joint, lowest of 25 starts"),
        "joint_single_start": (MUTED, "^", "joint, single start"),
    }
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    fig.patch.set_facecolor(SURFACE)
    ypos = list(range(len(order)))[::-1]
    for ax, key, scale, xlabel, title in (
        (axes[0], "d_make", 100.0, "change in make probability, B2 - B1 [percentage points]", "Horizon term: effect on putts holed"),
        (axes[1], "d_mean_miss", 100.0, "change in mean lateral miss, B2 - B1 [cm]", "Horizon term: effect on the miss (clipped at 1 m)"),
    ):
        ax.axvline(0.0, color=AXIS, linewidth=1.2)
        for j, form in enumerate(forms):
            color, marker, label = form_style[form]
            offset = 0.22 * (1 - j)
            vals = [scale * ht[k][form]["all"][key] for k in order]
            errs = [1.96 * scale * ht[k][form]["all"][key + "_se"] for k in order]
            ax.errorbar(vals, [y + offset for y in ypos], xerr=errs, fmt=marker, color=color, ecolor=color, elinewidth=2.0,
                        capsize=0, markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.2, label=label)
        ax.set_yticks(ypos)
        ax.set_yticklabels([FRINGE_LABEL[k] for k in order] if ax is axes[0] else [""] * len(order))
        ax.set_ylim(-0.6, len(order) - 0.4)
        _style(ax, xlabel, "", title)
        ax.grid(True, axis="x", color=GRID, linewidth=0.8)
        ax.grid(False, axis="y")
    axes[0].tick_params(axis="y", labelsize=9, colors=INK_2)
    _legend(axes[1], loc="upper right")
    fig.text(0.01, -0.03, "Points: paired difference over all putts; bars: 95 % interval. Right of zero is better on the left "
             "panel, left of zero is better on the right panel.", fontsize=8, color=MUTED)
    names.append(os.path.basename(_save(fig, out_dir, "fig4_horizon_test.png")))
    plt.close(fig)

    # ---- 5: range error ---------------------------------------------------------
    rng = summary["main"]["diagnostics"]["range"]
    fig, ax = plt.subplots(figsize=(6.6, 4.1))
    fig.patch.set_facecolor(SURFACE)
    for key, label, color, marker in (
        ("stereo_rms", "stereo only", METHOD_COLOR["B0"], "o"),
        ("mono_rms", "stick height only (where available)", METHOD_COLOR["B1"], "s"),
        ("fused_rms", "fused", METHOD_COLOR["B2"], "^"),
    ):
        xs = [d for d, k in zip(dists, dkeys) if rng[k].get(key) is not None]
        ys = [100.0 * rng[k][key] for k in dkeys if rng[k].get(key) is not None]
        ax.plot(xs, ys, color=color, marker=marker, markersize=6.5, markeredgecolor=SURFACE, markeredgewidth=1.2,
                linewidth=2.0, label=label)
    _style(ax, "putt length [m]", "RMS range error [% of distance]", "Range to the flagstick (GL1: f = 657 px, b = 20.0 mm)")
    ax.set_xticks(dists)
    ax.set_ylim(0.0, None)
    _legend(ax, loc="upper left")
    names.append(os.path.basename(_save(fig, out_dir, "fig5_range_error.png")))
    plt.close(fig)

    # ---- 6: cross-slope error budget -----------------------------------------------
    se_tab = summary["main"]["diagnostics"]["slope_error"]
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    fig.patch.set_facecolor(SURFACE)
    ax.plot(dists, [1e3 * se_tab[k]["representativeness"] for k in dkeys], color=INK, linewidth=1.6, linestyle=(0, (4, 2)),
            marker="o", markersize=5.5, markeredgecolor=SURFACE, markeredgewidth=1.0,
            label="true slope at the ball vs. true path average")
    for m in ("B1", "B0S", "SURVEY2", "SURVEY3"):
        _line(ax, dists, [1e3 * se_tab[k]["cross"][m] for k in dkeys], m)
    ax.axhline(summary["meta"]["nominal_seat_mrad"], color=AXIS, linewidth=1.0)
    ax.annotate("seating noise of one placement", (dists[-1], summary["meta"]["nominal_seat_mrad"]), xytext=(0, -11),
                textcoords="offset points", ha="right", fontsize=8, color=MUTED)
    _style(ax, "putt length [m]", "RMS error of the mean cross slope [mrad]", "What limits the read: one local sample vs. the path average")
    ax.set_xticks(dists)
    ax.set_ylim(0.0, None)
    _legend(ax, loc="upper left")
    names.append(os.path.basename(_save(fig, out_dir, "fig6_cross_slope_error.png")))
    plt.close(fig)

    # ---- 7: confidence calibration -----------------------------------------------------
    cal = {m: v["bins"] for m, v in summary["main"]["diagnostics"]["confidence"].items()}
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    fig.patch.set_facecolor(SURFACE)
    ax.plot([0, 1], [0, 1], color=AXIS, linewidth=1.2)
    for m in ("B1", "B0S", "SURVEY3"):
        rows = [r for r in cal[m] if r["n"] >= 20]
        _line(ax, [r["mean_confidence"] for r in rows], [r["within_hole"] for r in rows], m)
    _style(ax, "confidence score shown by the device", "fraction of reads within the hole radius",
           "Confidence score against outcome (perfect execution)")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.02)
    _legend(ax, loc="upper left")
    names.append(os.path.basename(_save(fig, out_dir, "fig7_confidence_calibration.png")))
    plt.close(fig)

    # ---- 8: by green class -----------------------------------------------------------------
    classes = summary["meta"]["classes"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    fig.patch.set_facecolor(SURFACE)
    methods = ("B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05")
    width = 0.12
    for j, m in enumerate(methods):
        xs = [i + (j - (len(methods) - 1) / 2.0) * (width + 0.015) for i in range(len(classes))]
        ax.bar(xs, [100.0 * nominal[m]["by_class"][c]["median_miss"] for c in classes], width=width,
               color=METHOD_COLOR[m], label=METHOD_LABEL[m], linewidth=0)
    _style(ax, "green class (all putt lengths pooled)", "median lateral miss [cm]", "Median miss by green class")
    ax.set_xticks(range(len(classes)))
    ax.set_xticklabels(classes)
    ax.grid(False, axis="x")
    ax.tick_params(axis="x", labelsize=9.5, colors=INK_2)
    _legend(ax, loc="upper left", ncol=2)
    names.append(os.path.basename(_save(fig, out_dir, "fig8_by_class.png")))
    plt.close(fig)

    # ---- 9: the three unmeasured inputs ----------------------------------------------------------
    sw = summary["sweeps"]
    panels = (
        ("seating_ext_mrad", "true seating noise [mrad per axis]", "Seating noise"),
        ("transfer_deg", "aim-transfer error [deg, 1 sigma]", "Reading the line off the puck"),
        ("relief_mm", "metre-scale relief of the green [mm RMS]", "Smoothness of the green"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.2), sharey=True)
    fig.patch.set_facecolor(SURFACE)
    base = sw["baseline"]
    for ax, (key, xlabel, title) in zip(axes, panels):
        levels = [k for k in sw[key] if k.replace(".", "", 1).isdigit()]
        xs = [float(k) for k in levels]
        for m in ("B1", "B0S", "SURVEY3"):
            _line(ax, xs, [100.0 * sw[key][k][m]["overall"]["make_perfect"] for k in levels], m)
        for m in ("HUMAN05", "HUMAN10"):
            if key == "relief_mm":
                ys = [100.0 * sw[key][k][m]["overall"]["make_perfect"] for k in levels]
            else:
                ys = [100.0 * base[m]["overall"]["make_perfect"]] * len(levels)
            ax.plot(xs, ys, color=METHOD_COLOR[m], linewidth=1.6, linestyle=(0, (4, 2)), label=METHOD_LABEL[m])
        _style(ax, xlabel, "putts holed, perfect stroke [%]" if ax is axes[0] else "", title)
        ax.set_xticks(xs)
        ax.set_ylim(0.0, None)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=8.5, frameon=False, labelcolor=INK_2,
               bbox_to_anchor=(0.5, -0.07))
    names.append(os.path.basename(_save(fig, out_dir, "fig9_unmeasured_inputs.png")))
    plt.close(fig)
    return names


# --------------------------------------------------------------------------
# the report: small accessors
# --------------------------------------------------------------------------


def _ov(summary, method, key, seat=None):
    return _seat(summary, seat)[method]["overall"][key]


def _bd(summary, method, d, key, seat=None):
    return _seat(summary, seat)[method]["by_distance"][d][key]


def _pick(dkeys: Sequence[str], wanted: Sequence[str]) -> List[str]:
    return [d for d in wanted if d in dkeys] or list(dkeys[:2])


def _first_beyond_hole(summary, method) -> Optional[str]:
    """Shortest putt length at which the method's median miss exceeds the hole radius."""
    for d in _dkeys(summary):
        if _bd(summary, method, d, "median_miss") > ph.HOLE_R:
            return d
    return None


def _significant(delta: dict, key: str = "d_make") -> int:
    """+1 / -1 if the paired difference is beyond 2 standard errors, else 0."""
    se = delta[key + "_se"]
    if se <= 0.0:
        return 0
    z = delta[key] / se
    return 1 if z > 2.0 else (-1 if z < -2.0 else 0)


def _standing(delta: dict, key: str = "d_make") -> str:
    """Words for a paired difference X minus Y: 'ahead of', 'behind' or
    'indistinguishable from' (inside 2 standard errors)."""
    return {1: "ahead of", -1: "behind", 0: "indistinguishable from"}[_significant(delta, key)]


def _pm(delta: dict, key: str = "d_make", scale: float = 100.0, digits: int = 1) -> str:
    return _ci(delta, key, scale, digits)


def _mk(tables: dict, method: str, key: str = "make_perfect", digits: int = 1) -> str:
    return _pct(tables[method]["overall"].get(key), digits)


def _band(summary, pair: str, key: str = "d_make") -> dict:
    """Break-even seating noise of ``pair`` ("B1_vs_HUMAN05"): from the main
    run where it lies inside the main levels, else from the sweep's wider
    range.  Adds ``source``."""
    main = summary["main"]["seating_breakeven_mrad"].get(pair, {}).get(key)
    if main and main["mid"] is not None:
        return {**main, "source": "main run"}
    sweep = summary["sweeps"]["seating_breakeven_mrad"].get(pair, {}).get(key)
    if sweep:
        return {**sweep, "source": "sweep subset"}
    return {**main, "source": "main run"}


def _fmt_band(band: dict) -> str:
    """'2.5 mrad (cannot be told apart between 1.7 and 3.3 mrad)' and its edge cases."""
    lo = f"{band['lo']:.1f}" if band["lo"] is not None else (f"below {band['first_level']:g}" if not band["ahead_at_first"] else None)
    hi = f"{band['hi']:.1f}" if band["hi"] is not None else (f"beyond {band['last_level']:g}" if not band["behind_at_last"] else None)
    if band["mid"] is None:
        where = (f"beyond {band['last_level']:g} mrad (the range tested)" if not band["behind_at_last"] and band["hi"] is None and band["lo"] is None and band["ahead_at_first"]
                 else f"not crossed between {band['first_level']:g} and {band['last_level']:g} mrad")
        if band["lo"] is not None:
            where += f"; not distinguishable at 2 standard errors from {band['lo']:.1f} mrad on"
        return where
    text = f"{band['mid']:.1f} mrad"
    if lo is not None and hi is not None:
        text += f" (not distinguishable at 2 standard errors from {lo} to {hi} mrad)"
    return text


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------


def _headline(summary) -> str:
    dk = _dkeys(summary)
    nom = _seat(summary)
    paired = summary["main"]["diagnostics"]["paired"]
    d_a, d_b = (_pick(dk, ("3", "6")) + dk)[:2]
    rows = []
    for m in HEADLINE:
        t = nom[m]
        vs = paired.get(f"{m}_vs_HUMAN05")
        rows.append([
            METHOD_LABEL[m],
            _pct(t["overall"]["make_perfect"], 1),
            _pct(t["overall"]["make_human"], 1),
            _cm(t["overall"]["median_miss"]),
            _pct(t["by_distance"][d_a]["make_perfect"]),
            _pct(t["by_distance"][d_b]["make_perfect"]),
            f"{_pm(vs)} / {_pm(vs, 'd_make_human')}" if vs else "-",
        ])
    return _table(
        ["Method", "holed, perfect stroke [%]", "holed, human execution [%]", "median lateral miss [cm]",
         f"holed at {d_a} m [%]", f"holed at {d_b} m [%]", "minus the 0.5 % reader [pp]: perfect / human execution"],
        rows,
    )


def _sensor_table(summary) -> str:
    nom = _seat(summary)
    paired = summary["main"]["diagnostics"]["paired"]
    adds = {
        "STRAIGHT": "camera bearing and range, entered green speed (no slope reading)",
        "B0": "+ puck tilt (accelerometer)",
        "B1": "+ flag-base height (elevation of the lowest visible point of the stick)",
        "B2": "+ turf-horizon profile (anchored fit)",
        "ORACLE": "the true surface, speed and grain (not a sensor: the ceiling)",
    }
    rows = []
    prev = None
    for m in SENSOR_CHAIN:
        o = nom[m]["overall"]
        step = paired.get(f"{m}_vs_{prev}") if prev else None
        rows.append([
            m, adds[m], _pct(o["make_perfect"], 1), _pct(o["make_human"], 1), _cm(o["median_miss"]), _cm(o["p90_miss"]),
            _cm(o["median_pace_err"], 0), _pct(o["short"]),
            f"{_pm(step)} pp, {_pm(step, 'd_mean_miss', 100.0, 2)} cm" if step else "-",
        ])
        prev = m
    return _table(
        ["Step", "What it adds", "holed, perfect stroke [%]", "holed, human execution [%]", "median miss [cm]", "90th pct miss [cm]",
         "median pace error [cm]", "short of the hole [%]", "gain over the row above: makes, mean miss (± 95 %)"],
        rows,
    )


def _horizon_tables(summary) -> str:
    ht = summary["main"]["horizon_test"]
    diag = summary["main"]["diagnostics"]
    flag = diag["flag"]
    dkeys = _dkeys(summary)
    order = [k for k in ("no_fringe", "no_surround", "realistic", "mounded") if k in ht]
    forms = [f for f in FIT_LABEL if f in ht[order[0]]]
    out = []
    rows = []
    for k in order:
        for f in forms:
            a = ht[k][f]["all"]
            rows.append([
                FRINGE_LABEL[k], FIT_LABEL[f], _ci(a, "d_make", 100.0, 1), _ci(a, "d_mean_miss", 100.0, 2),
                f"{_cm(a['median_miss_a'])} -> {_cm(a['median_miss_b'])}", _pct(a["b_closer"]), a["verdict"],
            ])
    out.append(_table(
        ["Silhouette seen by the camera", "Form of the horizon fit", "Δ make prob. [pp]", "Δ mean miss [cm]",
         "median miss B1 -> B2 [cm]", "B2 closer in [%] of putts", "verdict"], rows))
    out.append("")
    out.append(
        "Δ = B2 minus B1 on the same putts with the same noise, ± 95 % interval. \"Mean miss\" clips each miss at 1 m. "
        "Verdict rule (fixed before looking at the numbers): each of the two measures counts as moved when it changes by "
        "more than 2 standard errors; \"helps\" / \"hurts\" need both to move the same way, otherwise the verdict names the "
        "one that moved."
    )
    out.append("")
    rows = []
    for k in order:
        row = [FRINGE_LABEL[k]]
        for c in summary["meta"]["classes"]:
            e = ht[k]["anchored"][c]
            row.append(f"{100 * e['d_make']:+.1f} pp, {100 * e['d_mean_miss']:+.1f} cm ({e['verdict']})")
        rows.append(row)
    out.append("Anchored fit (B2) by green class:")
    out.append("")
    out.append(_table(["Silhouette"] + list(summary["meta"]["classes"]), rows))
    out.append("")
    # what the forms do to the quantities the puck measures directly
    se_all = diag["slope_error"]["all"]
    names = [("B1", "B1 (no horizon)"), ("B2", FIT_LABEL["anchored"]), ("B2C", FIT_LABEL["anchored_free_c"]),
             ("B2J", FIT_LABEL["joint"]), ("B2L", FIT_LABEL["joint_single_start"])]
    rows = []
    for key, label in names:
        if key not in se_all["cross"]:
            continue
        fits = ht["realistic"]["fits"].get({"B2": "anchored", "B2C": "anchored_free_c", "B2J": "joint"}.get(key, ""), {})
        rows.append([
            label, _mrad(se_all["along_at_ball"][key], 2), _mrad(se_all["cross_at_ball"][key], 2),
            _mrad(se_all["along_base_visible"][key], 2), _mrad(se_all["cross"][key], 2),
            _pct(fits.get("first_start_not_lowest"), 1) if fits else "-",
        ])
    out.append("What each form does to the quantities the device measures directly (realistic silhouette, camera reads, RMS "
               "error against the truth [mrad]):")
    out.append("")
    out.append(_table(
        ["Fit", "fitted along-line slope at the ball", "fitted cross slope at the ball",
         "mean along-line slope, base visible", "mean cross slope along the line",
         "fits in which another start found a lower minimum than the first [%]"], rows))
    out.append("")
    hw = summary["sweeps"]["horizon_sigma_mrad"]
    sig = list(hw["realistic"].keys())
    rows = []
    for k in order:
        if k not in hw:
            continue
        row = [FRINGE_LABEL[k]]
        for s in sig:
            v = hw[k][s]["vs_B1"]
            row.append(f"{100 * v['d_make']:+.1f} pp, {100 * v['d_mean_miss']:+.1f} cm ({v['verdict']})")
        rows.append(row)
    out.append(f"Weight of the horizon residuals, anchored fit (sweep subset, {summary['meta']['n_putts_sweep']} putts; "
               "per-sample sigma of the horizon residual, default 1 mrad):")
    out.append("")
    out.append(_table(["B2 vs B1 at sigma_horizon ="] + [f"{s} mrad" for s in sig], rows))
    out.append("")
    dom = summary["sweeps"]["horizon_domain_m"]
    rows = [[f"{k} m", _pct(v["at_boundary"], 1), _ci(v["vs_B1"], "d_make", 100.0, 1), _ci(v["vs_B1"], "d_mean_miss", 100.0, 2),
             v["vs_B1"]["verdict"]] for k, v in dom.items()]
    out.append("Extent of the modelled terrain (sweep subset; the ray-march stops where the terrain model ends, so a silhouette "
               "formed there is an artefact of the simulation):")
    out.append("")
    out.append(_table(["Half-width of the terrain model", "horizon samples formed at the edge of the model [%]",
                       "Δ make prob., B2 - B1 [pp]", "Δ mean miss [cm]", "verdict"], rows))
    out.append("")
    rows = [[f"{d} m", _pct(flag["by_distance"][d].get("horizon_on_green")), _pct(flag["by_distance"][d].get("horizon_on_collar")),
             _pct(flag["by_distance"][d].get("horizon_on_rough")),
             f"{flag['by_distance'][d].get('horizon_distance_median', float('nan')):.1f}"] for d in dkeys]
    out.append("What forms the silhouette in the realistic case (share of the horizon samples):")
    out.append("")
    out.append(_table(["Putt", "putting surface [%]", "collar [%]", "rough / surrounds [%]", "median distance of the silhouette [m]"], rows))
    return "\n".join(out)


def _sweep_rows(entries: Dict[str, dict], methods: Sequence[str], dkeys: Sequence[str]) -> List[List[str]]:
    """Rows 'variant | method | median miss at each distance | overall miss | make | pace' of a sweep."""
    rows = []
    for label, tables in entries.items():
        for m in methods:
            if m not in tables:
                continue
            o = tables[m]["overall"]
            rows.append(
                [label, m]
                + [_cm(tables[m]["by_distance"][d]["median_miss"]) for d in dkeys]
                + [_cm(o["median_miss"]), _pct(o["make_perfect"], 1), _cm(o["median_pace_err"], 0)]
            )
    return rows


def _sweep_table(first: str, entries: Dict[str, dict], methods: Sequence[str], dkeys: Sequence[str]) -> str:
    header = [first, "Method"] + [f"miss {d} m" for d in dkeys] + ["miss all [cm]", "make all [%]", "pace err [cm]"]
    return _table(header, _sweep_rows(entries, methods, dkeys))


def _level_table(first: str, entries: Dict[str, dict], methods: Sequence[str], key: str = "make_perfect",
                 suffix: str = "", extra: Optional[Dict[str, List[str]]] = None, extra_header: Sequence[str] = ()) -> str:
    """One row per sweep level, one column per method (overall value of ``key`` [%])."""
    rows = []
    for label, tables in entries.items():
        row = [label + suffix] + [_pct(tables[m]["overall"].get(key), 1) if m in tables else "-" for m in methods]
        if extra:
            row += extra.get(label, ["-"] * len(extra_header))
        rows.append(row)
    return _table([first] + list(methods) + list(extra_header), rows)


def _closed_form() -> str:
    rows = []
    for r in bench.closed_form_table():
        rows.append([
            f"{100 * r['slope']:g} %", f"{r['stimp']:g}", f"{r['theory']:.6f}", f"{r['phi_2m']:.6f}", f"{r['phi_4m']:.6f}",
            f"{r['phi_8m']:.6f}", f"{r['ratio']:.4f}",
        ])
    ref = bench.reference_point()
    text = _table(["Cross slope", "Stimp", "theory (5/14) G s / a_r [rad]", "solved, 2 m", "solved, 4 m", "solved, 8 m", "solved / theory"], rows)
    text += (
        "\n\nThe solved angle is independent of distance (the three columns agree to better than 1e-4 relative) and exceeds "
        "the first-order formula by the neglected second-order term (0.1 % at 0.5 % slope on a slow green, 3 % at 2 % slope "
        "on a fast one). Reference point: 10 ft, 1 % cross slope, Stimp 10, 0.43 m past the hole gives an aim offset of "
        f"**{ref['aim_offset']:.4f} m** (phi {ref['phi']:.5f} rad, v0 {ref['v0']:.4f} m/s); the paced small-slope formula "
        f"gives {ref['theory_offset']:.4f} m. Known value: about 0.14 m."
    )
    return text


# --------------------------------------------------------------------------
# narrative (numbers and directions are derived from the summary)
# --------------------------------------------------------------------------


def _headline_text(summary) -> str:
    meta = summary["meta"]
    dk = _dkeys(summary)
    diag = summary["main"]["diagnostics"]
    paired = diag["paired"]
    ht = summary["main"]["horizon_test"]
    sw = summary["sweeps"]
    d_a, d_b = (_pick(dk, ("3", "6")) + dk)[:2]
    lim = {m: _first_beyond_hole(summary, m) for m in ("B1", "B0S", "SURVEY3")}
    tr = sw["transfer_vs_human"]
    tr_keys = [k for k in tr if k.replace(".", "", 1).isdigit()]
    rl = sw["relief_paired"]
    rl_keys = [k for k in rl if k != "0"]
    gr_pair = paired["B1_GRAIN_vs_B1"]
    ex = sw["execution"]
    ex_keys = list(ex)

    def vs(m, h="HUMAN05"):
        p = paired[f"{m}_vs_{h}"]
        return f"{_standing(p)} him ({_pm(p)} pp with a perfect stroke, {_pm(p, 'd_make_human')} pp with human execution)"

    def hz(key):
        a = ht[key]["anchored"]["all"]
        return f"{a['verdict']} ({_pm(a)} pp makes, {_pm(a, 'd_mean_miss', 100.0, 2)} cm mean miss)"

    dom = sw["horizon_domain_m"]
    dom_keys = list(dom)
    lines = [
        f"- **A read is worth a lot.** Aiming straight holes {_pct(_ov(summary, 'STRAIGHT', 'make_perfect'), 1)} % of all putts "
        f"with a perfect stroke; the Quick Read (B1) holes {_pct(_ov(summary, 'B1', 'make_perfect'), 1)} % and cuts the median "
        f"miss from {_cm(_ov(summary, 'STRAIGHT', 'median_miss'))} cm to {_cm(_ov(summary, 'B1', 'median_miss'))} cm. At "
        f"{d_a} m it holes {_pct(_bd(summary, 'B1', d_a, 'make_perfect'))} % against {_pct(_bd(summary, 'STRAIGHT', d_a, 'make_perfect'))} %, "
        f"at {d_b} m {_pct(_bd(summary, 'B1', d_b, 'make_perfect'))} % against {_pct(_bd(summary, 'STRAIGHT', d_b, 'make_perfect'))} %.",
        f"- **Against a golfer who reads the cross slope to 0.5 %** (and who, like the shipping device, does not know the "
        f"grain): the Quick Read is {vs('B1')}; the Precision Read is {vs('B0S')}; the three-drop Survey is {vs('SURVEY3')}. "
        f"Against a 1 % reader the Quick Read is {_standing(paired['B1_vs_HUMAN10'])} him by {_pm(paired['B1_vs_HUMAN10'])} pp.",
        "- **That standing rests on four inputs nobody has measured** (section 4):",
        f"  - *Seating noise of the puck on turf* ({meta['nominal_seat_mrad']:g} mrad assumed). With a perfect stroke the Quick "
        f"Read equals the 0.5 % reader at {_fmt_band(_band(summary, 'B1_vs_HUMAN05'))} of seating noise and the 1 % reader at "
        f"{_fmt_band(_band(summary, 'B1_vs_HUMAN10'))}; the Survey equals the 0.5 % reader at "
        f"{_fmt_band(_band(summary, 'SURVEY3_vs_HUMAN05'))}.",
        f"  - *Reading the line off the puck* ({meta['sigma_transfer_deg']:g} deg assumed, plus the {meta['display_step_deg']:.2f} deg "
        f"steps of the 1-bit display). Quick Read minus 0.5 % reader: "
        + ", ".join(f"{_pm(tr[k]['B1_vs_HUMAN05'])} pp at {k} deg" for k in tr_keys) + ".",
        f"  - *Metre-scale smoothness of the green* (the synthetic greens are smooth below about 15 m wavelength). Quick Read "
        "minus 0.5 % reader with added relief of "
        + ", ".join(f"{k} mm RMS: {_pm(rl[k]['B1_vs_HUMAN05'])} pp" for k in rl_keys) + ".",
        f"  - *The grain.* The grain sensor ships disabled, so every device number here is without it. Switched on and working "
        f"as specified it would add {_pm(gr_pair)} pp to the Quick Read; a human who reads the grain equally well gains "
        f"{_pm(paired['HUMAN05_GRAIN_vs_HUMAN05'])} pp.",
        f"- **No mode reads a long putt to within the hole.** The median miss exceeds the hole radius (5.4 cm) from "
        f"{lim['B1'] or 'no length tested'} m on for the Quick Read, from {lim['B0S'] or 'no length tested'} m for the Precision "
        f"Read and from {lim['SURVEY3'] or 'no length tested'} m for the three-drop Survey (medians at {d_b} m: "
        f"{_cm(_bd(summary, 'B1', d_b, 'median_miss'))}, {_cm(_bd(summary, 'B0S', d_b, 'median_miss'))} and "
        f"{_cm(_bd(summary, 'SURVEY3', d_b, 'median_miss'))} cm). For a single placement the reason is that the slope under the "
        "ball differs from the average slope along the line (section 8).",
        f"- **The tilt does nearly all the work on the line.** B0 (tilt only) and B1 have the same median miss "
        f"({_cm(_ov(summary, 'B0', 'median_miss'))} cm and {_cm(_ov(summary, 'B1', 'median_miss'))} cm). The flag-base height "
        f"improves the pace, not the line: median pace error at {d_b} m {_cm(_bd(summary, 'B0', d_b, 'median_pace_err'), 0)} cm "
        f"for B0 against {_cm(_bd(summary, 'B1', d_b, 'median_pace_err'), 0)} cm for B1; B1 holes {_pm(paired['B1_vs_B0'])} pp more "
        "putts than B0 (section 3).",
        f"- **Turf horizon (B2 against B1, same putts).** With no fringe at all (optimistic): {hz('no_fringe')}. With the "
        f"realistic geometry as modelled: {hz('realistic')}; extending the terrain model from {dom_keys[0]} m to "
        f"{dom_keys[-1]} m changes that to {_pm(dom[dom_keys[-1]]['vs_B1'])} pp and "
        f"{_pm(dom[dom_keys[-1]]['vs_B1'], 'd_mean_miss', 100.0, 2)} cm ({dom[dom_keys[-1]]['vs_B1']['verdict']}, sweep subset). "
        f"With mounded surrounds: {hz('mounded')}. The firmware default is B1 (section 5).",
        f"- **More placements beat more optics.** Precision Read: {_pm(paired['B0S_vs_B1'])} pp makes over B1; three-drop "
        f"Survey: {_pm(paired['SURVEY3_vs_B1'])} pp, with the median miss falling from {_cm(_ov(summary, 'B1', 'median_miss'))} cm "
        f"to {_cm(_ov(summary, 'SURVEY3', 'median_miss'))} cm. Camera presets and lens height change next to nothing (section 11).",
        f"- **Two limits no slope sensor removes.** With the true surface but the golfer's entered green speed "
        f"({100 * meta['sensor_params']['sigma_stimp']:g} % error) and no grain knowledge, only "
        f"{_pct(_ov(summary, 'ORACLE_SLOPE', 'make_perfect'), 1)} % of putts drop with a perfect stroke. And with human execution "
        f"at the specified {meta['sigma_dir_deg']:g} deg / {100 * meta['sigma_speed']:g} % - an elite level - even the oracle holes "
        f"{_pct(_ov(summary, 'ORACLE', 'make_human'), 1)} %; at {ex_keys[2] if len(ex_keys) > 2 else ex_keys[-1]}, nearer a club "
        f"golfer, the oracle holes {_mk(ex[ex_keys[2] if len(ex_keys) > 2 else ex_keys[-1]], 'ORACLE', 'make_human')} % and the "
        f"Quick Read {_mk(ex[ex_keys[2] if len(ex_keys) > 2 else ex_keys[-1]], 'B1', 'make_human')} % (section 9).",
    ]
    return "\n".join(lines)


def _sensor_text(summary) -> str:
    paired = summary["main"]["diagnostics"]["paired"]
    nom = _seat(summary)
    b2 = paired["B2_vs_B1"]
    b2_words = {1: "a gain", -1: "a loss", 0: "no change that can be told from zero"}[_significant(b2)]
    return (
        f"Read down the table. The camera and the entered green speed alone (STRAIGHT) hole "
        f"{_pct(nom['STRAIGHT']['overall']['make_perfect'], 1)} % with a perfect stroke. The **tilt** is the step that matters: "
        f"{_pm(paired['B0_vs_STRAIGHT'])} pp. The **flag-base height** adds {_pm(paired['B1_vs_B0'])} pp of makes and nothing "
        f"measurable to the line ({_pm(paired['B1_vs_B0'], 'd_mean_miss', 100.0, 2)} cm of mean miss); what it buys is pace "
        f"(median pace error {_cm(nom['B0']['overall']['median_pace_err'], 0)} cm -> {_cm(nom['B1']['overall']['median_pace_err'], 0)} cm). "
        f"The **turf horizon**, in the anchored form and with the realistic silhouette as modelled, gives {_pm(b2)} pp of "
        f"makes - {b2_words} - and {_pm(b2, 'd_mean_miss', 100.0, 2)} cm of mean miss; section 5 shows that even this depends "
        f"on the surrounds and on how far the terrain is modelled. The gap from the Quick Read to the oracle "
        f"({_pm(paired['ORACLE_vs_B1'])} pp with a perfect stroke, {_pm(paired['ORACLE_vs_B1'], 'd_make_human')} pp with human "
        "execution) is what no sensor on this "
        "device closes: the surface between ball and hole, the true green speed and the grain."
    )


def _seat_text(summary) -> str:
    meta = summary["meta"]
    seats = [f"{s:g}" for s in meta["seat_levels_mrad"]]
    dk = _dkeys(summary)
    main = summary["main"]
    sw = summary["sweeps"]
    se_tab = main["diagnostics"]["slope_error"]
    d_mid = _pick(dk, ("6",))[0]
    pbs = main["paired_by_seat"]
    human_better = [d for d in dk if _bd(summary, "HUMAN05", d, "median_miss") < _bd(summary, "B1", d, "median_miss")]

    def versus(method, human):
        return ", ".join(f"{_pm(pbs[s][f'{method}_vs_{human}'])} pp at {s} mrad" for s in seats)

    ahead_high = [m for m in ("B1", "B0S", "SURVEY2", "SURVEY3") if _significant(pbs[seats[-1]][f"{m}_vs_HUMAN05"]) > 0]
    behind_high = [m for m in ("B1", "B0S", "SURVEY2", "SURVEY3") if _significant(pbs[seats[-1]][f"{m}_vs_HUMAN05"]) < 0]
    ext = sw["seating_ext_mrad"]
    ext_keys = list(ext)
    out = [
        "Paired differences in make probability with a perfect stroke (device mode minus human baseline, ± 95 %):",
        "",
        f"- Quick Read (B1) minus the 0.5 % reader: {versus('B1', 'HUMAN05')}; minus the 1 % reader: {versus('B1', 'HUMAN10')}.",
        f"- Precision Read (B0S) minus the 0.5 % reader: {versus('B0S', 'HUMAN05')}.",
        f"- Survey (SURVEY3) minus the 0.5 % reader: {versus('SURVEY3', 'HUMAN05')}.",
        "",
        "Break-even seating noise: the level at which the paired difference to the human baseline is zero, by linear "
        f"interpolation between the levels run (main run: {', '.join(seats)} mrad; beyond that the sweep subset: "
        f"{', '.join(ext_keys)} mrad). In brackets the band inside which the two cannot be told apart at 2 standard errors:",
        "",
        _table(
            ["Mode", "equals the 0.5 % reader at (perfect stroke)", "(human execution)", "equals the 1 % reader at (perfect stroke)",
             "(human execution)"],
            [[m] + [_fmt_band(_band(summary, f"{m}_vs_{h}", key)) for h in ("HUMAN05", "HUMAN10") for key in ("d_make", "d_make_human")]
             for m in ("B1", "B0S", "SURVEY3")],
        ),
        "",
        "Three things follow.",
        "",
        "1. The device's standing against a good human reader is decided by a number nobody has measured. At "
        f"{seats[-1]} mrad the modes that are still ahead of the 0.5 % reader beyond 2 standard errors are: "
        f"{', '.join(ahead_high) if ahead_high else 'none'}; behind him: {', '.join(behind_high) if behind_high else 'none'}. "
        f"At {ext_keys[-1]} mrad ({float(ext_keys[-1]) * 46e-3:.2f} mm under one edge of the 46 mm puck) the Quick Read holes "
        f"{_mk(ext[ext_keys[-1]], 'B1')} % against {_mk(sw['baseline'], 'HUMAN10')} % for the 1 % reader. Measuring the seating "
        "repeatability of the real puck on real turf is the first experiment the project needs.",
        f"2. Lower seating noise has diminishing returns for single-placement modes. Going from {seats[1]} to {seats[0]} mrad "
        f"raises B1 by {100 * (_ov(summary, 'B1', 'make_perfect', seats[0]) - _ov(summary, 'B1', 'make_perfect')):.1f} pp, because "
        "the error that remains is the difference between the slope under the ball and the average along the line "
        f"({_mrad(se_tab[d_mid]['representativeness'])} mrad RMS at {d_mid} m, section 8), which no single placement sees.",
        "3. The simulated human baselines read the PATH-AVERAGE cross slope and know the hole height and the bearing "
        "exactly; only the size of the read error is varied, and they aim without any display. That is generous to the "
        "human on long, contoured putts. Lengths at which the 0.5 % reader has a smaller median miss than B1 at "
        f"{meta['nominal_seat_mrad']:g} mrad: {', '.join(d + ' m' for d in human_better) if human_better else 'none'}.",
    ]
    return "\n".join(out)


def _transfer_text(summary) -> str:
    meta = summary["meta"]
    sw = summary["sweeps"]
    tr = sw["transfer_deg"]
    tp = sw["transfer_vs_human"]
    paired = summary["main"]["diagnostics"]["paired"]
    keys = [k for k in tr if k.replace(".", "", 1).isdigit()]
    ideal = [k for k in tr if k not in keys]
    flip = None
    for k in keys:
        if _significant(tp[k]["B1_vs_HUMAN05"]) < 0:
            flip = k
            break
    out = [
        "The device shows a LINE; the golfer has to start the ball along it. Two things stand between the computed aim and "
        f"the ball: the 1-bit, 128 x 128 display can only draw the {meta['display_line_px']:g} px line in direction steps of "
        f"{meta['display_step_deg']:.2f} deg (hardware, {meta['display_step_deg'] / math.sqrt(12.0):.2f} deg RMS), and the golfer "
        f"has to set the ball or the putter to a 22 mm line by eye (assumed {meta['sigma_transfer_deg']:g} deg, 1 sigma; no data). "
        "Neither applies to the human baselines, who aim at a spot they chose themselves. The execution noise of section 9 "
        "is separate and applies to everybody.",
        "",
        f"- With the display quantisation alone (0 deg) the Quick Read is {_standing(tp['0']['B1_vs_HUMAN05'])} the 0.5 % reader "
        f"({_pm(tp['0']['B1_vs_HUMAN05'])} pp); "
        + (f"from {flip} deg of transfer error on it is behind him beyond 2 standard errors "
           f"({_pm(tp[flip]['B1_vs_HUMAN05'])} pp)." if flip else "at no level tested does it fall behind him beyond 2 standard errors.")
        + (f" An ideal display without quantisation would be worth {100 * (tr[ideal[0]]['B1']['overall']['make_perfect'] - tr['0']['B1']['overall']['make_perfect']):+.1f} pp "
           f"to the Quick Read and {100 * (tr[ideal[0]]['SURVEY3']['overall']['make_perfect'] - tr['0']['SURVEY3']['overall']['make_perfect']):+.1f} pp to the Survey."
           if ideal else ""),
        f"- The assumption used elsewhere in this report for the reverse task - pointing the puck at the hole by hand - is "
        f"{math.degrees(meta['sensor_params']['sigma_hand_bearing']):g} deg. If reading the line back were that poor, the Quick "
        f"Read would be at {_pm(tp[keys[-1]]['B1_vs_HUMAN05'])} pp against the 0.5 % reader.",
        "- **The other use model.** If the golfer ignores the line and uses the displayed break in cup widths, aiming by eye "
        "relative to the hole he can see, there is no quantisation and no transfer error (and the measured bearing no longer "
        f"matters for the aim). On the same reads that model gives the Quick Read {_pct(_ov(summary, 'B1_CUPS', 'make_perfect'), 1)} % "
        f"({_pm(paired['B1_CUPS_vs_B1'])} pp over following the line; {_pm(paired['B1_CUPS_vs_HUMAN05'])} pp against the 0.5 % reader) "
        f"and the Survey {_pct(_ov(summary, 'SURVEY3_CUPS', 'make_perfect'), 1)} % ({_pm(paired['SURVEY3_CUPS_vs_HUMAN05'])} pp against "
        "the 0.5 % reader). It assumes the golfer places the aim point exactly; judging \"1.4 cups left\" at 6 m has an error "
        "of its own that is not modelled. Every table in this report other than the rows marked \"cups\" assumes the golfer "
        "follows the line.",
    ]
    return "\n".join(out)


def _relief_text(summary) -> str:
    sw = summary["sweeps"]
    rl = sw["relief_mm"]
    rp = sw["relief_paired"]
    added = sw["relief_added_slope"]
    dk = _dkeys(summary)
    keys = [k for k in rl if k != "0"]
    d3 = _pick(dk, ("3",))[0]
    worst = keys[-1]
    behind = [k for k in keys if _significant(rp[k]["B1_vs_HUMAN05"]) < 0]
    out = [
        "The generated greens are built from waves of 15 m wavelength and longer: the slope at a point and the mean slope "
        "half a metre around it differ by less than 0.3 mrad, so one 46 mm tilt sample is as representative of the first "
        "metre of the putt as it can possibly be. Real turf has relief at the metre scale; how much is not known. The sweep "
        "adds a random field with wavelengths of 1-3 m to the surface the ball rolls on and the puck sits on (same putts, "
        "same noise draws; the human baselines read the path average of the new surface).",
        "",
        f"- Added slope per axis: " + ", ".join(f"{_mrad(added[k])} mrad at {k} mm" for k in keys) + ".",
        f"- Quick Read, all lengths: " + ", ".join(f"{_mk(rl[k], 'B1')} % at {k} mm" for k in rl)
        + f"; at {d3} m: " + ", ".join(f"{_pct(rl[k]['B1']['by_distance'][d3]['make_perfect'])} %" for k in rl) + ".",
        "- The Precision Read re-reads the same spot. Its gain over the Quick Read "
        + ("shrinks" if rp[worst]["B0S_vs_B1"]["d_make"] < rp["0"]["B0S_vs_B1"]["d_make"] else "does not shrink")
        + " with the relief: " + ", ".join(f"{_pm(rp[k]['B0S_vs_B1'])} pp at {k} mm" for k in rp) + ".",
        "- The Survey samples three spots. Against the smooth green it changes by "
        + ", ".join(f"{_pm(rp[k]['SURVEY3_vs_smooth'])} pp at {k} mm" for k in keys)
        + " (Quick Read: " + ", ".join(f"{_pm(rp[k]['B1_vs_smooth'])} pp" for k in keys) + f"); at {worst} mm it is "
        f"{_standing(rp[worst]['SURVEY3_vs_HUMAN05'])} the 0.5 % reader ({_pm(rp[worst]['SURVEY3_vs_HUMAN05'])} pp).",
        "- Quick Read against the 0.5 % reader: "
        + (f"behind beyond 2 standard errors at {', '.join(behind)} mm." if behind else "not behind beyond 2 standard errors at any level tested.")
        + " The amplitudes are an assumption, not data: the first field experiment should include the tilt at spots "
        "0.3-1 m apart on real greens.",
    ]
    return "\n".join(out)


def _horizon_verdict(summary) -> str:
    ht = summary["main"]["horizon_test"]
    dom = summary["sweeps"]["horizon_domain_m"]
    dom_keys = list(dom)
    last = dom[dom_keys[-1]]["vs_B1"]

    def clause(key, form="anchored"):
        a = ht[key][form]["all"]
        return f"**{a['verdict']}** ({_ci(a, 'd_make', 100.0, 1)} pp makes, {_ci(a, 'd_mean_miss', 100.0, 2)} cm mean miss)"

    real = ht["realistic"]["anchored"]["all"]
    sign_real = verdict_sign(real["verdict"])
    sign_far = verdict_sign(last["verdict"])
    if sign_real > 0 and sign_far <= 0:
        reading = ("That gain does not survive a larger terrain model, so it is not evidence that the horizon helps on a real "
                   "course: the plain reading for the realistic case is **no reliable effect**.")
    elif sign_real > 0:
        reading = "The gain survives a larger terrain model; the plain reading for the realistic case is **a small gain**."
    elif sign_real < 0:
        reading = "The plain reading for the realistic case is **it hurts**."
    else:
        reading = "The plain reading for the realistic case is **no measurable effect**."
    return (
        f"**Verdict, stated plainly (anchored fit, the estimator's B2).** With no fringe at all (optimistic) the horizon term "
        f"{clause('no_fringe')}. With the realistic geometry as this simulator models it - collar, rough, smooth surrounds "
        f"that mostly fall away - the result is: {clause('realistic')}; with the terrain modelled out to {dom_keys[-1]} m "
        f"instead of {dom_keys[0]} m it is {_ci(last, 'd_make', 100.0, 1)} pp and {_ci(last, 'd_mean_miss', 100.0, 2)} cm "
        f"({last['verdict']}; sweep subset). {reading} With mounded surrounds that are independent of the green "
        f"(pessimistic) it {clause('mounded')}."
    )


def _horizon_text(summary) -> str:
    ht = summary["main"]["horizon_test"]
    diag = summary["main"]["diagnostics"]
    flag = diag["flag"]
    se_all = diag["slope_error"]["all"]
    dk = _dkeys(summary)
    seats = [f"{s:g}" for s in summary["meta"]["seat_levels_mrad"]]
    rough = [flag["by_distance"][d].get("horizon_on_rough") for d in dk if flag["by_distance"][d].get("horizon_on_rough") is not None]
    hd = [flag["by_distance"][d].get("horizon_distance_median") for d in dk if flag["by_distance"][d].get("horizon_distance_median") is not None]
    pbs = summary["main"]["paired_by_seat"]
    by_seat = ", ".join(
        f"{100 * (_ov(summary, 'B2', 'make_perfect', s) - _ov(summary, 'B1', 'make_perfect', s)):+.1f} pp at {s} mrad" for s in seats
    )
    del pbs
    gains = [_ov(summary, "B2", "make_perfect", s) - _ov(summary, "B1", "make_perfect", s) for s in seats]
    rising = all(b > a for a, b in zip(gains[:-1], gains[1:]))
    fits = {k: ht[k]["fits"] for k in ht}
    dom = summary["sweeps"]["horizon_domain_m"]
    dom_last = dom[list(dom)[-1]]["vs_B1"]
    v_nf = ht["no_fringe"]["anchored"]["all"]["verdict"]
    v_real = ht["realistic"]["anchored"]["all"]["verdict"]
    v_mound = ht["mounded"]["anchored"]["all"]["verdict"]
    s_nf = verdict_sign(ht["no_fringe"]["anchored"]["all"]["verdict"])
    s_real = verdict_sign(ht["realistic"]["anchored"]["all"]["verdict"])
    s_far = verdict_sign(dom_last["verdict"])
    s_mound = verdict_sign(ht["mounded"]["anchored"]["all"]["verdict"])
    robust = s_nf > 0 and s_real > 0 and s_far > 0 and s_mound >= 0
    decision = (
        f"**Decision for the firmware default: {summary['meta']['default_method']} (horizon off).** Verdicts for the horizon "
        f"term: \"{v_nf}\" when the camera sees the smooth continuation of the green; \"{v_real}\" with the fringe as "
        f"modelled at the default extent of the terrain model and \"{dom_last['verdict']}\" at the largest one; \"{v_mound}\" "
        "with greenside shaping. "
        + ("In this simulator the gain holds in every geometry tested; the default nevertheless stays off until it is "
           "confirmed on real greens, because nothing above the turf line is modelled." if robust else
           "The device cannot tell which of these cases it is in.")
        + " B2 remains selectable (`estimate(meas, \"B2\")`) so that logged horizon profiles from real greens with surveyed "
        "slopes can settle the question."
    )
    j_real, j_mound = ht["realistic"]["joint"]["all"], ht["mounded"]["joint"]["all"]
    l_real = ht["realistic"]["joint_single_start"]["all"]
    c_real, c_mound = ht["realistic"]["anchored_free_c"]["all"], ht["mounded"]["anchored_free_c"]["all"]
    a_mound = ht["mounded"]["anchored"]["all"]
    out = [
        "What the numbers mean:",
        "",
        f"- **The silhouette is mostly not the putting surface.** In the realistic case {_pct(min(rough))}-{_pct(max(rough))} % of "
        f"the horizon samples are formed by the rough and the ground beyond it, at a median distance of {min(hd):.0f}-{max(hd):.0f} m "
        f"from the lens; {_pct(flag['horizon_at_model_boundary'], 1)} % of all samples "
        f"({_pct(flag['horizon_rough_at_model_boundary'], 1)} % of those formed by rough and surrounds) sit exactly where the "
        "ray leaves the modelled terrain, i.e. their height is set by where the simulated world ends. The reviewers' premise "
        "is confirmed.",
        "- **The answer depends on the form of the fit, which is itself a finding.** The literal joint MAP problem (all "
        "parameters, all rows) has many local minima: a single Levenberg-Marquardt run from the tilt plane ends in a "
        f"non-global one in {_pct(fits['realistic']['joint']['first_start_not_lowest'])} % of realistic reads, "
        f"{_pct(fits['no_fringe']['joint']['first_start_not_lowest'])} % without fringe and "
        f"{_pct(fits['mounded']['joint']['first_start_not_lowest'])} % with mounds. An earlier version of this report was "
        f"produced with that single run and concluded that the horizon helps in the realistic case (here: {_pm(l_real)} pp, "
        f"{_pm(l_real, 'd_mean_miss', 100.0, 2)} cm). The lowest minimum of the same cost gives {_pm(j_real)} pp and "
        f"{_pm(j_real, 'd_mean_miss', 100.0, 2)} cm ({j_real['verdict']}) and, with mounds, {_pm(j_mound)} pp "
        f"({j_mound['verdict']}). The earlier gain came from the optimiser stopping near its B1-like start, not from the "
        "stated objective.",
        "- **Why the joint fit goes wrong.** The 41 horizon samples are treated as 41 independent 1 mrad measurements, but "
        "their errors are common-mode: the silhouette is whatever stands behind the green, at a height the patch model does "
        "not know. A height error common to all samples has the same signature as the along-line slope `a` (cos θ, 0.9-1 "
        f"across the field), so the fit moves `a`: its RMS error at the ball is {_mrad(se_all['along_at_ball']['B2J'], 1)} mrad "
        f"against {_mrad(se_all['along_at_ball']['B1'], 1)} mrad for the tilt reading it started from.",
        "- **What the anchored fit does instead.** B2 holds what the Quick Read measures directly - the slopes at the ball "
        "(tilt) and the along-line curvature (hole height) - gives the silhouette height a free offset, and lets the horizon "
        "determine only how the surface tilts across the field (the twist `d` and the cross curvature `e`). Its minimum is "
        f"start-independent in practice (another start is lower in {_pct(fits['realistic']['anchored']['first_start_not_lowest'], 2)} % "
        f"of realistic reads) and it leaves the slope at the ball, the fall line and the along-line profile as in B1. A variant "
        f"that lets `c` move as well "
        f"scores more makes in the realistic case ({_pm(c_real)} pp) and is harmless with mounds ({_pm(c_mound)} pp), but only "
        f"because the silhouette height then goes into `c`: its mean along-line slope with the base visible is wrong by "
        f"{_mrad(se_all['along_base_visible']['B2C'], 1)} mrad against {_mrad(se_all['along_base_visible']['B1'], 1)} mrad for B1, "
        "i.e. it overrules the flag-base height and wrecks the pace. It is shown for completeness, not offered.",
        f"- **Mounds.** With mounds and hollows of 0.2 m RMS behind the green the anchored fit {a_mound['verdict']} "
        f"({_pm(a_mound)} pp, {_pm(a_mound, 'd_mean_miss', 100.0, 2)} cm), and the device flags a poor horizon on "
        f"{_pct(fits['mounded']['anchored']['poor_horizon'])} % of those reads (against "
        f"{_pct(fits['realistic']['anchored']['poor_horizon'])} % in the realistic case) - a warning, but not a cure. A 0.2 m mound "
        "seen from 12 m stands 17 mrad high and is several metres wide: to the fit it is a tilt across the field, not an outlier.",
        f"- **Seating noise.** B2 minus B1 in make probability with the realistic silhouette: {by_seat}. "
        + ("The horizon is worth more when the tilt is worse, as it should be if it carries some independent information; "
           "at the nominal level that information is too weak to show reliably." if rising else
           "There is no consistent trend with the seating noise."),
        "- **What is not in the simulation at all.** Trees, buildings, spectators, bunker lips and the flagstick's own "
        "surroundings above the turf line; errors in picking the turf silhouette out of the image; sun glare; a wet or "
        "dirty window. The surround terrain itself (both the default and the mounded variant) is an assumption with named "
        "parameters, not survey data. None of the omitted effects makes a silhouette more trustworthy.",
        "",
        decision,
    ]
    return "\n".join(out)


def _range_text(summary) -> str:
    dk = _dkeys(summary)
    rng = summary["main"]["diagnostics"]["range"]
    sw = summary["sweeps"]
    fh = sw["range_first_hole"]
    far = dk[-1]
    mid = _pick(dk, ("9",))[0]
    near = _pick(dk, ("3",))[0]
    cam_tab = sw["camera"]
    cam_rng = sw["camera_range"]
    best = "2MP" if "2MP" in cam_tab else list(cam_tab)[-1]
    sy = sw["systematics"]
    plus = sy.get("disparity bias +0.1 px")
    minus = sy.get("disparity bias -0.1 px")
    cam = summary["meta"]["camera"]
    out = [
        f"- Stereo alone follows the textbook formula: {_pct(rng[near]['stereo_rms'], 1)} % at {near} m, "
        f"{_pct(rng[mid]['stereo_rms'], 1)} % at {mid} m, {_pct(rng[far]['stereo_rms'], 1)} % at {far} m. The estimate "
        f"`f b / disparity` is biased long by about the square of that ({_pct(rng[far]['stereo_bias'], 1)} % at {far} m); "
        "this is not corrected.",
        f"- Ranging from the stick's angular height needs the top inside the {cam['up_fov_deg']:g} deg "
        "upward field (beyond about 6.7 m for a 2.13 m stick) AND a visible base. It is therefore available on "
        f"{_pct(rng[mid]['mono_available'])} % of the reads at {mid} m and {_pct(rng[far]['mono_available'])} % at {far} m, "
        f"where it is good ({_pct(rng[far]['mono_rms'], 1)} % with a learned stick height, {_pct(fh[far]['mono_rms'], 1)} % with "
        "the first-hole default of 2.13 m; the simulated sticks are 2.0-2.3 m, the 7 % is the uncertainty the estimator "
        "assigns to that default).",
        f"- Fused: {_pct(rng[mid]['fused_rms'], 1)} % at {mid} m and {_pct(rng[far]['fused_rms'], 1)} % at {far} m over all reads "
        f"(first hole: {_pct(fh[mid]['fused_rms'], 1)} % and {_pct(fh[far]['fused_rms'], 1)} %). The design-spec figure of "
        "\"about 2-3 % once the stick height is learned\" is met only on the reads where the stick-height channel is "
        "available; on crowned lines, where the base is hidden, the range falls back to stereo.",
        "- **The table above is random error only.** Every optical error in it is zero-mean. A systematic disparity error - "
        f"stereo calibration drift - is not: 0.1 px is {1e3 * 0.1 / cam['f_px']:.2f} mrad of relative yaw between the two "
        f"cameras, which a bow of the board of {0.1 / cam['f_px'] * cam['baseline'] / 8.0 * 1e6:.2f} µm (sagitta) across the "
        f"{1e3 * cam['baseline']:g} mm baseline would produce."
        + (f" At +0.1 px the fused range reads {_pct(plus['range'][mid]['fused_bias'], 1)} % at {mid} m (RMS error "
           f"{_pct(plus['range'][mid]['fused_rms'], 1)} %) and {_pct(plus['B1']['overall']['short'])} % of perfectly struck putts "
           f"stop short (baseline {_pct(sy['baseline']['B1']['overall']['short'])} %); at -0.1 px it reads "
           f"{_signed(100 * minus['range'][mid]['fused_bias'], 1)} % ({_pct(minus['range'][mid]['fused_rms'], 1)} % RMS). The learned "
           "stick height cannot remove a stereo scale error, because it is learned from stereo."
           + (f" Reading the range LONG is not a loss here: at -0.1 px B1 holes {_pm(minus['vs_baseline'])} pp against the "
              "baseline. With the green-speed error as large as it is, a target pace of 0.30 m past the hole leaves many putts "
              "short, and anything that makes the device hit firmer recovers some of them. The 0.30 m target was specified, "
              "not optimised; this affects every method alike." if minus["vs_baseline"]["d_make"] > 0.0 else "")
           if plus and minus else ""),
        f"- Range hardly matters for the line: the {best} preset ranges to {_pct(cam_rng[best][far]['fused_rms'], 1)} % at {far} m "
        f"and its B1 median miss over all lengths is {_cm(cam_tab[best]['B1']['overall']['median_miss'])} cm against "
        f"{_cm(cam_tab['GL1']['B1']['overall']['median_miss'])} cm for GL1. Range feeds the displayed distance and the pace.",
    ]
    return "\n".join(out)


def _flag_text(summary) -> str:
    dk = _dkeys(summary)
    diag = summary["main"]["diagnostics"]
    fl = diag["flag"]["by_distance"]
    se_tab = diag["slope_error"]
    fb = summary["sweeps"]["flag_base"]
    blind_key = [k for k in fb if k.startswith("base visibility unknown")][0]
    hid_cls = diag["flag"]["hidden_by_distance_class"]
    nom = _seat(summary)
    near, far = dk[0], dk[-1]
    mid = _pick(dk, ("6",))[0]
    cam = summary["meta"]["camera"]
    out = [
        f"- **Detection.** The flag is found on {_pct(fl[near]['found'], 1)} % of reads at {near} m and "
        f"{_pct(fl[far]['found'], 1)} % at {far} m (2 % floor, loss of the 12.7 mm stick at long range, and the visor pointing "
        f"more than {cam['half_fov_h_deg']:g} deg off the flag about 1 % of the time). A read without the flag falls back to "
        "hand-pointing; on those putts every device mode is as poor as FLAGOUT (section 12, subset \"flag_not_found\"). The "
        "detection model is an engineering guess; section 11 shows a 20 % floor.",
        f"- **Hidden base.** From {1e3 * cam['h_cam']:g} mm above the turf a gently crowned line hides "
        f"the bottom of the stick: on {_pct(fl[near]['base_hidden'], 1)} % of putts at {near} m, {_pct(fl[mid]['base_hidden'])} % "
        f"at {mid} m and {_pct(fl[far]['base_hidden'])} % at {far} m, with a median of "
        f"{1e3 * fl[far]['hidden_height_median']:.0f} mm of stick hidden at {far} m. By class at {far} m: "
        + ", ".join(f"{c} {_pct(hid_cls[f'{far}|{c}'])} %" for c in summary["meta"]["classes"]) + ".",
        f"- **Consequence for the pace.** With the base visible B1 knows the mean slope along the line to "
        f"{_mrad(se_tab[mid]['along_base_visible']['B1'])} mrad RMS at {mid} m; with the base hidden only to "
        f"{_mrad(se_tab[mid]['along_base_hidden']['B1'])} mrad (the tilt alone: {_mrad(se_tab[mid]['along_base_hidden']['B0'])} mrad). "
        "The one-sided bound is a weak constraint: the fit sits at the tilt plane or on the bound, never below it, so on "
        "crowned lines B1 expects the hole at least as high as it is. Mean pace error of B1 at "
        f"{mid} m: {_signed(100 * nom['B1']['by_distance'][mid]['mean_pace_err'])} cm, against "
        f"{_signed(100 * nom['ORACLE_SLOPE']['by_distance'][mid]['mean_pace_err'])} cm with the true surface.",
        f"- **The device is assumed to know whether the base is hidden.** That flag comes from the simulator's line-of-sight "
        "test; real firmware has to infer it. The sweep in section 11 shows that nothing is lost if it cannot: treating the "
        f"lowest visible point as the base in every case gives B1 {_pct(fb[blind_key]['B1']['overall']['make_perfect'], 1)} % "
        f"makes against {_pct(fb['with flag base']['B1']['overall']['make_perfect'], 1)} % with perfect knowledge "
        f"(paired difference {_ci(summary['sweeps']['flag_base_paired']['B1_blind_vs_informed'], 'd_make', 100.0, 1)} pp).",
    ]
    return "\n".join(out)


def _budget_text(summary) -> str:
    dk = _dkeys(summary)
    diag = summary["main"]["diagnostics"]
    se_tab = diag["slope_error"]
    se_all = se_tab["all"]
    seat = summary["meta"]["nominal_seat_mrad"]
    bias = 1e3 * summary["meta"]["sensor_params"]["sigma_tilt_bias"]
    single = math.hypot(seat, bias)
    cross = None
    for d in dk:
        if 1e3 * se_tab[d]["representativeness"] > single:
            cross = d
            break
    mid = _pick(dk, ("6",))[0]
    far = _pick(dk, ("9",))[0]
    sd = _seat(summary)
    out = [
        f"- **Line.** A single placement measures the slope under the ball with {single:.1f} mrad per axis (seating "
        f"{seat:g} mrad and device bias {bias:g} mrad). The slope it should have measured - the average along the line - "
        f"differs from the slope under the ball by {_mrad(se_tab[dk[0]]['representativeness'])} mrad RMS at {dk[0]} m, "
        f"{_mrad(se_tab[mid]['representativeness'])} mrad at {mid} m and {_mrad(se_tab[far]['representativeness'])} mrad at {far} m "
        "(all classes pooled; on these smooth synthetic greens - see section 4.3)."
        + (f" From {cross} m on, this representativeness error is larger than the measurement error." if cross else "")
        + f" The two add in quadrature to the B1 column. The Precision Read shrinks only the first term (to "
        f"{seat / math.sqrt(2.0):.1f} mrad if the two seatings are independent); the Survey attacks "
        f"the second ({_mrad(se_tab[mid]['cross']['SURVEY3'])} mrad at {mid} m against {_mrad(se_tab[mid]['cross']['B1'])} mrad for B1).",
        f"- **What the display shows for the slope at the ball** is the tilt reading itself, for every method: RMS error "
        f"{se_all['slope_pct']['B1']:.2f} % slope for a single placement and {se_all['slope_pct']['B0S']:.2f} % for the "
        "Precision Read. No fit - with or without horizon - is allowed to change it. (The fitted patch of B2 has the same "
        f"slopes at the ball as B1, {_mrad(se_all['along_at_ball']['B2'], 2)} mrad along the line; the joint horizon fit of "
        f"section 5 would have shown {_mrad(se_all['along_at_ball']['B2J'], 1)} mrad.)",
        f"- **Pace.** The median pace error of B1 at {mid} m is {_cm(sd['B1']['by_distance'][mid]['median_pace_err'], 0)} cm; "
        f"with the true surface and the same entered green speed it is still "
        f"{_cm(sd['ORACLE_SLOPE']['by_distance'][mid]['median_pace_err'], 0)} cm. A "
        f"{100 * summary['meta']['sensor_params']['sigma_stimp']:g} % error in the entered Stimp is a "
        f"{100 * summary['meta']['sensor_params']['sigma_stimp']:g} % error in roll-out, about "
        f"{100 * summary['meta']['sensor_params']['sigma_stimp'] * (float(mid) + 0.3):.0f} cm at {mid} m, larger than the "
        f"0.30 m of intended over-run: {_pct(sd['ORACLE_SLOPE']['by_distance'][mid]['short'])} % of perfectly struck "
        f"{mid} m putts stop short even with perfect knowledge of the surface. Green-speed knowledge, not slope sensing, "
        "sets the pace accuracy of every mode. B2's along-line slope and pace are identical to B1's by construction "
        "(section 5).",
    ]
    return "\n".join(out)


def _exec_text(summary) -> str:
    meta = summary["meta"]
    dk = _dkeys(summary)
    sw = summary["sweeps"]
    ex = sw["execution"]
    ep = sw["execution_paired"]
    keys = list(ex)
    rows = []
    for d in _pick(dk, ("1.5", "3", "6")):
        o = _bd(summary, "ORACLE", d, "make_human")
        b = _bd(summary, "B1", d, "make_human")
        s3 = _bd(summary, "SURVEY3", d, "make_human")
        rows.append(
            f"- {d} m: execution alone costs {100 * (1 - o):.0f} pp (the oracle holes {_pct(o)} %); the Quick Read costs a further "
            f"{100 * (o - b):.1f} pp ({_pct(b, 1)} %); the Survey gives {100 * (s3 - b):.1f} pp of that back ({_pct(s3, 1)} %)."
        )
    far = dk[-1]
    cap = sw["capture"]
    ck = list(cap)
    cpp = sw["capture_paired"]
    first, last = keys[0], keys[-1]
    out = [
        f"With {meta['sigma_dir_deg']:g} deg of direction scatter and {100 * meta['sigma_speed']:g} % of speed scatter (the "
        "specified default), the make probability splits as follows:",
        "",
        *rows,
        "",
        f"**That default is an elite putter.** With a perfect read on a perfectly smooth green it holes "
        + ", ".join(f"{_pct(_bd(summary, 'ORACLE', d, 'make_human'))} % at {d} m" for d in dk)
        + ". Commonly quoted tour averages at about these lengths are roughly 77 / 40 / 23 / 15 / 7 / 4 % (quoted from "
        "memory, not computed here), so the specified execution noise describes a better-than-tour putter; the device is a "
        "training aid for golfers who do not putt like that. The execution sweep (sweep subset, same reads) shows what a "
        "read is worth to them:",
        "",
        _table(
            ["Execution (direction / speed, 1 sigma)"] + [m for m in ex[first]]
            + ["B1 minus 1 % reader [pp]", "B1 minus 0.5 % reader [pp]", "ORACLE minus B1 [pp]"],
            [[k] + [_mk(ex[k], m, "make_human") for m in ex[k]]
             + [_pm(ep[k]["B1_vs_HUMAN10"], "d_make_human"), _pm(ep[k]["B1_vs_HUMAN05"], "d_make_human"),
                _pm(ep[k]["ORACLE_vs_B1"], "d_make_human")] for k in keys],
        ),
        "",
        f"Make probability with human execution [%], all lengths pooled. From {first} to {last} the whole value of a perfect "
        f"read (ORACLE minus STRAIGHT) shrinks from "
        f"{100 * (ex[first]['ORACLE']['overall']['make_human'] - ex[first]['STRAIGHT']['overall']['make_human']):.1f} pp to "
        f"{100 * (ex[last]['ORACLE']['overall']['make_human'] - ex[last]['STRAIGHT']['overall']['make_human']):.1f} pp, the Quick "
        f"Read's gain over no read from {_pm(ep[first]['B1_vs_STRAIGHT'], 'd_make_human')} pp to "
        f"{_pm(ep[last]['B1_vs_STRAIGHT'], 'd_make_human')} pp, and what a perfect read would add on top of the Quick Read from "
        f"{_pm(ep[first]['ORACLE_vs_B1'], 'd_make_human')} pp to {_pm(ep[last]['ORACLE_vs_B1'], 'd_make_human')} pp. For a typical "
        "amateur the read is not the bottleneck; the stroke is.",
        "",
        f"On long putts nobody holes much: at {far} m the oracle holes {_pct(_bd(summary, 'ORACLE', far, 'make_human'), 1)} % "
        f"and B1 {_pct(_bd(summary, 'B1', far, 'make_human'), 1)} % at the default execution level. There the product's value is "
        "the leave, not the make, and that is governed by the pace (section 8).",
        "",
        f"**Capture rule.** With Penner's quadratic speed limit instead of the default ({ck[-1]}) every method loses about "
        f"{100 * (cap[ck[0]]['B1']['overall']['make_perfect'] - cap[ck[-1]]['B1']['overall']['make_perfect']):.0f} pp "
        f"(B1 {_mk(cap[ck[-1]], 'B1')} % with a perfect stroke, {_mk(cap[ck[-1]], 'B1', 'make_human')} % with human execution) and no "
        f"comparison changes: B1 minus the 0.5 % reader is {_pm(cpp[ck[-1]]['B1_vs_HUMAN05'])} pp against "
        f"{_pm(cpp[ck[0]]['B1_vs_HUMAN05'])} pp with the default rule.",
    ]
    return "\n".join(out)


def _bearing_text(summary) -> str:
    sw = summary["sweeps"]
    fp = sw["flagout_2x2_paired"]
    paired = summary["main"]["diagnostics"]["paired"]
    hand = math.degrees(summary["meta"]["sensor_params"]["sigma_hand_bearing"])
    dial = 100 * summary["meta"]["sensor_params"]["sigma_user_distance"]
    k_bd, k_bt = "bearing, at the dialled distance", "bearing, at the true distance"
    k_dh, k_dt = "distance, with the hand bearing", "distance, with the true bearing"
    cups = fp["FLAGOUT, cups against line"]
    return (
        f"Both tables use the same tilt-only plane; FLAGOUT replaces the camera's bearing (about 1 mrad) by hand-pointing "
        f"({hand:g} deg, 1 sigma) AND the camera's range by a dialled distance ({dial:g} %). The camera is worth "
        f"{_pm(paired['B0_vs_FLAGOUT'])} pp of make probability in total (main run). The 2 x 2 table splits that: the bearing "
        f"alone is worth {_pm(fp[k_bd])} pp with the dialled distance and {_pm(fp[k_bt])} pp with the true distance; the "
        f"distance alone {_pm(fp[k_dh])} pp with the hand bearing and {_pm(fp[k_dt])} pp with the true bearing. The bearing is "
        "the larger part, the range is not negligible (it sets the pace: fewer putts short).\n\n"
        f"The value of the bearing exists only under the follow-the-line use model. If the golfer uses the break in cups "
        f"relative to the hole he can see, hand-pointing costs almost nothing: FLAGOUT then holes "
        f"{_mk(sw['flagout_2x2']['hand bearing, dialled distance, break-in-cups use model'], 'FLAGOUT')} % "
        f"({_pm(cups)} pp over following the line), close to the true-bearing row. A pointing error of {hand:g} deg is "
        f"{100 * 3.0 * math.tan(math.radians(hand)):.1f} cm at 3 m, more than the hole radius, before any slope error. The "
        f"{hand:g} deg figure is an assumption about how well a golfer can aim a 46 mm puck by eye."
    )


def _sweep_text(summary) -> str:
    sw = summary["sweeps"]
    dk = _dkeys(summary)

    def o(entry, method, key="make_perfect"):
        return entry[method]["overall"][key]

    cam = sw["camera"]
    hh = sw["h_cam_mm"]
    fb = sw["flag_base"]
    fbp = sw["flag_base_paired"]
    st = sw["stimp_error_pct"]
    gr_ = sw["grain"]
    gv = sw["grain_vs_off"]
    gs = sw["grain_strong_greens"]
    gh = sw["grain_vs_human"]
    sp = sw["spin_seat_correlation"]
    sv = sw["survey_sigma_field_mrad"]
    lat = sw["survey_lateral_paired"]
    outl = sw["seating_outliers"]
    sy = sw["systematics"]
    gk = list(gr_.keys())
    svk = list(sv.keys())
    hk = [k for k in hh if "GL1" not in k]
    short = dk[0]
    far = dk[-1]
    ok = list(outl)
    worst_g = min((k for k in gv if k != gk[1]), key=lambda k: gv[k]["d_make"])
    lat_keys = list(lat)
    ghk = list(gh)

    stk = list(st)
    stimp_gain = ""
    if len(stk) >= 2:
        stimp_gain = (
            f"Going from {stk[1]} % to {stk[0]} % error is worth {100 * (o(st[stk[0]], 'B1') - o(st[stk[1]], 'B1')):+.1f} pp to B1 and "
            f"{100 * (o(st[stk[0]], 'ORACLE_SLOPE') - o(st[stk[1]], 'ORACLE_SLOPE')):+.1f} pp to a device that knew the surface "
            "exactly: the better the read, the more the green speed limits it. "
        )

    def sys_line(label):
        v = sy[label]
        return f"{label}: {_pct(v['B1']['overall']['make_perfect'], 1)} % ({_pm(v['vs_baseline'])} pp)"

    out = [
        f"- **Camera preset.** B1 make probability: " + ", ".join(f"{k} {_pct(o(v, 'B1'), 1)} %" for k, v in cam.items())
        + ". Focal length and baseline change the range accuracy and the flag-detection rate (QVGA finds the flag on "
        f"{_pct(sw['camera_found'].get('QVGA'), 0)} % of reads against {_pct(sw['camera_found'].get('GL1'), 0)} % for GL1), not the read.",
        f"- **Lens height.** B1 make probability "
        + ", ".join(f"{_pct(o(hh[k], 'B1'), 1)} % at {k} mm" for k in hk)
        + f"; the share of hidden bases goes from {_pct(hh[hk[0]]['base_hidden'])} % to {_pct(hh[hk[-1]]['base_hidden'])} %. "
        "A crown hides the base beyond sqrt(2 h / curvature), which grows only with the square root of the height.",
        f"- **Flag-base height.** Removing it changes B1 by {_pm(fbp['B1_with_vs_without'])} pp (with minus without) "
        f"and raises the median pace error from {_cm(o(fb['with flag base'], 'B1', 'median_pace_err'), 0)} to "
        f"{_cm(o(fb['without flag base'], 'B1', 'median_pace_err'), 0)} cm; the median lateral miss is unchanged "
        f"({_cm(o(fb['with flag base'], 'B1', 'median_miss'))} and {_cm(o(fb['without flag base'], 'B1', 'median_miss'))} cm). "
        f"For B2 the same comparison gives {_pm(fbp['B2_with_vs_without'])} pp: the anchored fit takes its along-line profile "
        "from the Quick Read, so the flag base serves it in the same way.",
        f"- **Entered green speed.** B1 make probability " + ", ".join(f"{_pct(o(v, 'B1'), 1)} % at {k} % error" for k, v in st.items())
        + "; with the true surface " + ", ".join(f"{_pct(o(v, 'ORACLE_SLOPE'), 1)} % at {k} %" for k, v in st.items())
        + ". " + stimp_gain + "Even with a perfectly known Stimp the true-surface reference stays below 100 % because it "
        "does not know the grain.",
        f"- **Grain.** The sensor ships disabled; that is the default of every other table. Switched on and working as "
        f"specified it is worth {_pm(gv[gk[1]])} pp to B1 ({_pct(o(gr_[gk[0]], 'B1'), 1)} % -> {_pct(o(gr_[gk[1]], 'B1'), 1)} %), "
        f"almost all of it on the {_pct(gs['fraction_of_putts'])} % of putts on strongly grained greens "
        f"({_pct(gs[gk[0]]['make_perfect'], 1)} % -> {_pct(gs[gk[1]]['make_perfect'], 1)} % there). The specified sensor model is "
        "purely multiplicative - it never reports grain where there is none and knows the direction of the weakest grain to "
        "20 deg - which no photometric sensor will do. With defects: "
        + "; ".join(f"{k}: {_pm(gv[k])} pp against no sensor" for k in gv if k != gk[1])
        + f". The worst of these ({worst_g}) is {_standing(gv[worst_g])} having no sensor at all. Against the 0.5 % reader: "
        + "; ".join(f"{k}: {_pm(gh[k])} pp" for k in ghk) + ".",
        f"- **Precision Read.** Its gain over B1 ({100 * (o(sp['0'], 'B0S') - o(sp['0'], 'B1')):+.1f} pp) assumes two "
        f"independent seatings. If half of the seating error is a property of the spot the gain is "
        f"{100 * (o(sp['0.5'], 'B0S') - o(sp['0'], 'B1')):+.1f} pp, and if all of it is (the spin only cancels the device bias) "
        f"{100 * (o(sp['1'], 'B0S') - o(sp['0'], 'B1')):+.1f} pp. Which of these is true is part of the unmeasured seating question; "
        "metre-scale relief (section 4.3) has the same effect.",
        f"- **Survey: placing the drops.** Once the puck is lifted from the ball position nothing marks the line; the drops "
        f"are placed by eye. A drop that is off the line has its \"toward the hole\" frame rotated, which leaks the along-line "
        "slope into its cross tilt (0.30 m off the line 1 m short of the hole is 17 deg). The estimator allows for 0.15 m. "
        "SURVEY3 minus B1: " + ", ".join(f"{_pm(lat[k]['SURVEY3_vs_B1'])} pp at {k} m" for k in lat_keys)
        + f". The gain {('survives to ' + lat_keys[-1] + ' m') if _significant(lat[lat_keys[-1]]['SURVEY3_vs_B1']) > 0 else ('is no longer beyond 2 standard errors at ' + lat_keys[-1] + ' m')}.",
        f"- **Survey model-error allowance.** With `sigma_field` = {svk[0]} SURVEY3 holes {_pct(o(sv[svk[0]], 'SURVEY3'), 1)} %, "
        f"with {svk[1]} {_pct(o(sv[svk[1]], 'SURVEY3'), 1)} %. It is kept because it keeps the Survey's stated uncertainty honest "
        "(section 12).",
        f"- **Seating outliers.** {ok[1]}: B1 {_pct(o(outl[ok[1]], 'B1'), 1)} %, B0S {_pct(o(outl[ok[1]], 'B0S'), 1)} %, SURVEY3 "
        f"{_pct(o(outl[ok[1]], 'SURVEY3'), 1)} %; {ok[2]}: {_pct(o(outl[ok[2]], 'B1'), 1)} %, {_pct(o(outl[ok[2]], 'B0S'), 1)} %, "
        f"{_pct(o(outl[ok[2]], 'SURVEY3'), 1)} % (no outliers: {_pct(o(outl[ok[0]], 'B1'), 1)} %, {_pct(o(outl[ok[0]], 'B0S'), 1)} %, "
        f"{_pct(o(outl[ok[0]], 'SURVEY3'), 1)} %). The Huber loss cannot reject an outlier when there is only one tilt reading.",
        "- **Systematic and out-of-range sensor errors** (B1; change against the baseline on the same putts): "
        + "; ".join(sys_line(k) for k in sy if k != "baseline" and not k.startswith("disparity"))
        + ". A ten times stronger mirage "
        + ("does not move the make probability measurably but" if _significant(sy["mirage x 10"]["vs_baseline"]) == 0 else "moves the make probability and")
        + f" degrades what the flag base is for: the "
        f"mean along-line slope with the base visible goes from {_mrad(sy['baseline']['along_base_visible'][far], 2)} to "
        f"{_mrad(sy['mirage x 10']['along_base_visible'][far], 2)} mrad at {far} m. If the cameras' level reference carries the "
        f"same accelerometer bias as the tilt it goes to {_mrad(sy['level reference shares the tilt bias']['along_base_visible'][far], 2)} mrad. "
        "The disparity-bias rows are discussed in section 6.",
    ]
    return "\n".join(out)


def _fusion_text(summary) -> str:
    diag = summary["main"]["diagnostics"]
    sub = diag["subsets"]
    nom = _seat(summary)
    conf = diag["confidence"]
    se_tab = diag["slope_error"]
    dk = _dkeys(summary)

    def cls(method, c, key="median_miss"):
        return nom[method]["by_class"][c][key]

    def sb(label, method, key="median_miss"):
        return sub[label][method].get(key)

    hid = "base_hidden (crowned line)"
    dbl = "double_break"
    far = _pick(dk, ("9",))[0]
    worse = (sb(dbl, "B1") or 0.0) > (sb(dbl, "STRAIGHT") or 0.0)
    b1, b0s, s3, b2 = conf["B1"], conf["B0S"], conf["SURVEY3"], conf["B2"]
    out = [
        "**Where it works.** On planar and gently contoured greens a single placement is representative of the line: B1's "
        f"median miss is {_cm(cls('B1', 'planar'))} cm on planar and {_cm(cls('B1', 'gentle'))} cm on gentle greens (all "
        f"lengths), the Precision Read {_cm(cls('B0S', 'planar'))} and {_cm(cls('B0S', 'gentle'))} cm. With the base visible "
        f"(N = {sub['base_visible']['B1']['n']}) B1 holes {_pct(sb('base_visible', 'B1', 'make_perfect'))} % against "
        f"{_pct(sb('base_visible', 'HUMAN05', 'make_perfect'))} % for the 0.5 % reader.",
        "",
        "**Where it does not.**",
        "",
        f"- *Contoured greens.* On undulating greens B1's median miss is {_cm(cls('B1', 'undulating'))} cm and on tiered "
        f"greens {_cm(cls('B1', 'tiered'))} cm; the Precision Read helps little there ({_cm(cls('B0S', 'undulating'))} and "
        f"{_cm(cls('B0S', 'tiered'))} cm) because the error is not seating noise. The Survey does "
        f"({_cm(cls('SURVEY3', 'undulating'))} and {_cm(cls('SURVEY3', 'tiered'))} cm).",
        f"- *Convex (crowned) lines.* When the base of the stick is hidden (N = {sub[hid]['B1']['n']}, mostly long putts on "
        f"contoured greens) B1's median miss is {_cm(sb(hid, 'B1'))} cm and it holes {_pct(sb(hid, 'B1', 'make_perfect'))} %; "
        f"B0 gives {_cm(sb(hid, 'B0'))} cm and {_pct(sb(hid, 'B0', 'make_perfect'))} %: on these putts the fusion adds "
        f"next to nothing to the tilt. SURVEY3 reaches {_cm(sb(hid, 'SURVEY3'))} cm and {_pct(sb(hid, 'SURVEY3', 'make_perfect'))} %.",
        f"- *Double breaks.* Where the cross slope changes sign along the line (N = {sub[dbl]['B1']['n']}) a single read is "
        + ("WORSE than no read" if worse else "no better than might be hoped")
        + f": B1 misses by a median of {_cm(sb(dbl, 'B1'))} cm, STRAIGHT by {_cm(sb(dbl, 'STRAIGHT'))} cm. The "
        f"puck reads the first break correctly and applies it to the whole putt. SURVEY3 gets {_cm(sb(dbl, 'SURVEY3'))} cm, "
        f"the 0.5 % human {_cm(sb(dbl, 'HUMAN05'))} cm. The device has no way of knowing from one placement that it is on "
        "such a putt.",
        f"- *Survey pace on long crowned putts.* SURVEY3's mean slope along the line is worse than SURVEY2's when the base "
        f"is hidden from the ball ({_mrad(se_tab[far]['along_base_hidden']['SURVEY3'])} against "
        f"{_mrad(se_tab[far]['along_base_hidden']['SURVEY2'])} mrad RMS at {far} m). The plane-plus-curvature model has two "
        "parameters for the slope along the line; the third drop adds a precise local height difference near the hole that "
        "this model cannot place correctly on a tiered or S-shaped profile. A piecewise slope field through the drops "
        "would be the natural next step; it was not implemented because the specification asks for plane plus curvature.",
        "",
        "**Confidence score.** The score is `erf(R_hole / (sqrt(2) sigma_lat))`, with `sigma_lat` built from the tilt "
        "reading error, an allowance for the slope changing along the line, the grain the solve does not know about and "
        "(flag missing) the hand-pointing error. The constants of the allowance were calibrated on these synthetic greens "
        "(they replace the 0.004 1/m curvature prior of the fit, which overstated the uncertainty of a single placement by "
        "about a factor of two), so the following is a consistency check, not a validation:",
        "",
        f"- *Calibration.* The claimed sigma of the mean cross slope is about right for every mode (RMS of error / sigma: "
        + ", ".join(f"{m} {conf[m]['z_rms']:.2f}" for m in conf) + "; 1 = exact). Mean score against the fraction of reads "
        "whose line passes within the hole radius: "
        + ", ".join(f"{m} {conf[m]['mean_confidence']:.2f} / {conf[m]['within_hole']:.2f}" for m in conf) + ".",
        f"- *It reflects the mode.* Mean score {b1['mean_confidence']:.3f} for the Quick Read, {b0s['mean_confidence']:.3f} for the "
        f"Precision Read, {s3['mean_confidence']:.3f} for the Survey, in the order of the fractions inside the hole radius "
        f"({b1['within_hole']:.3f}, {b0s['within_hole']:.3f}, {s3['within_hole']:.3f}). The horizon never raises it: B2's score is "
        f"B1's, lowered when the horizon is flagged as poor ({b2['mean_confidence']:.3f}).",
        f"- *What it does NOT do.* Within one mode the score is almost entirely a function of the putt length. Its rank "
        f"correlation with the absolute miss over all B1 reads is {b1['spearman_pooled']:.2f}, but minus the distance alone "
        f"gives {b1['spearman_minus_distance']:.2f}; inside one putt length the correlation is only "
        f"{b1['spearman_within_length']:.2f} for B1 ({b0s['spearman_within_length']:.2f} B0S, {s3['spearman_within_length']:.2f} "
        "SURVEY3). A golfer cannot use it to tell a good 6 m read from a bad 6 m read. It tells him how much to trust a "
        "read of this kind at this length, which he could also learn from a table.",
    ]
    return "\n".join(out)


def _limits_text(summary) -> str:
    meta = summary["meta"]
    sp = meta["sensor_params"]
    diag = summary["main"]["diagnostics"]
    rs = diag["roll_status"]
    n_rolls = sum(v["n"] + v["n_human"] for v in rs.values())
    n_time = sum(v["max_time"] + v["max_time_human"] for v in rs.values())
    n_oob = sum(v["out_of_bounds"] + v["out_of_bounds_human"] for v in rs.values())
    sw = summary["sweeps"]
    tp = sw["transfer_vs_human"]
    rp = sw["relief_paired"]
    rl_last = list(rp)[-1]
    paired = diag["paired"]
    pbs = summary["main"]["paired_by_seat"]
    seats = [f"{s:g}" for s in meta["seat_levels_mrad"]]
    ht = summary["main"]["horizon_test"]
    dom = sw["horizon_domain_m"]
    dom_last = dom[list(dom)[-1]]["vs_B1"]
    sub = diag["subsets"]["double_break"]
    dk = _dkeys(summary)
    mid = _pick(dk, ("9",))[0]
    mid6 = _pick(dk, ("6",))[0]
    flag_d = diag["flag"]["by_distance"]
    sy = sw["systematics"]
    b1h = paired["B1_vs_HUMAN05"]
    worse_seat = pbs[seats[-1]]["B1_vs_HUMAN05"]
    tr_levels = [k for k in tp if k.replace(".", "", 1).isdigit()]
    worse_tr = tp[tr_levels[-2] if len(tr_levels) > 1 else tr_levels[-1]]["B1_vs_HUMAN05"]
    worse_tr_key = tr_levels[-2] if len(tr_levels) > 1 else tr_levels[-1]
    real_words = {1: "a gain", -1: "a loss", 0: "no effect that can be told from zero"}
    out = [
        "**Unmeasured inputs that decide the result** (each is swept; none has data behind it):",
        "",
        f"- **Seating noise** ({1e3 * sp['sigma_seat']:g} mrad nominal; 1 to 10 mrad run, plus an outlier mixture). No published "
        "data. The Precision Read additionally assumes that two seatings on the same spot are independent (section 4.1, 11).",
        f"- **Aim transfer** ({meta['sigma_transfer_deg']:g} deg assumed): how well a golfer starts the ball along a 22 mm line "
        f"on the puck. No data. Quick Read minus the 0.5 % reader: "
        + ", ".join(f"{_pm(tp[k]['B1_vs_HUMAN05'])} pp at {k} deg" for k in tp if k.replace(".", "", 1).isdigit())
        + f" (section 4.2). The {meta['display_step_deg']:.2f} deg direction steps of the 1-bit display are hardware and are included.",
        "- **Metre-scale smoothness of the green**: the synthetic greens have none of the 1-3 m relief real turf has; "
        f"{rl_last} mm RMS of it changes the Quick Read by {_pm(rp[rl_last]['B1_vs_smooth'])} pp and cannot be engineered away in "
        "the puck (section 4.3).",
        "- **Grain**: the sensor is unproven and ships disabled, so the shipping device does not know the grain at all; the "
        "specified sensor model (20 deg, 30 %, purely multiplicative) is optimistic (section 11).",
        f"- **Survey drop placement** ({sp['sigma_survey_lateral']:g} m off the line assumed, by eye; section 11) and the "
        f"**hand-pointing error** ({math.degrees(sp['sigma_hand_bearing']):g} deg).",
        "- **Surround terrain** (default: mean radial slope -8 % to +2 % with slow azimuthal variation; stress case: 0.2 m RMS "
        "mounds) and the **extent of the terrain model**. Together they decide the horizon result (section 5).",
        f"- **Device tilt bias** {1e3 * sp['sigma_tilt_bias']:g} mrad per axis after the user's zeroing on a hard flat surface "
        "(read, turn 180 degrees in place, read again); 2.5 mrad is in section 11.",
        f"- **Stereo calibration drift** (none by default; ±0.1 and ±0.2 px in section 6), **mirage** "
        f"({sp['sigma_mirage']:g} 1/m; ten times that in section 11), **flag detection** (2 % floor; 20 % in section 11).",
        f"- **Entered green speed** ({100 * sp['sigma_stimp']:g} %): it sets the pace of every mode, and the better the read the "
        "more it limits the make probability (section 11).",
        f"- **Human execution**: {meta['sigma_dir_deg']:g} deg and {100 * meta['sigma_speed']:g} %, independent, Gaussian - an elite "
        "level; an amateur gets much less out of any read (section 9).",
        "- **Human baselines**: read error applied to the true path-average cross slope; perfect hole height, bearing and "
        "distance; no display to read; no grain knowledge unless stated. On long contoured putts this is generous to the human.",
        "- **Capture rule** (Holmes / Penner style: holed if the path passes within the hole radius slower than "
        "1.63 m/s x sqrt(1 - (delta/R)^2)); lip-outs do not deflect the ball. The alternative exponent moves every method "
        "by about 3 pp and no comparison (section 9).",
        "",
        "**Simplifications of the model:**",
        "",
        "- The ball rolls deterministically on a smooth surface: no bumpiness, footprints, wind or ball imbalance. Real "
        "putts scatter even with perfect execution, so all make probabilities with a \"perfect stroke\" are upper bounds.",
        "- Grain is a constant push; green speed is uniform over the green; the rough does not slow a ball that runs off.",
        "- The lens is taken to be at the ball position (the real cameras sit 16 mm ahead and 10 mm either side of the puck centre).",
        "- The device is told whether the base of the stick is visible (section 7), and the turf silhouette is assumed to be "
        "extracted from the image without error; nothing above the turf line exists in the simulated scene.",
        "- The estimator's noise constants stay at their nominal values when the true noise is varied.",
        "- The confidence score's constants and the horizon fit's form were chosen on these same synthetic greens; neither "
        "has seen real data.",
        "",
        "**Things that did not work as hoped, in one place:**",
        "",
        f"1. In the shipping configuration the Quick Read is {_standing(b1h)} a golfer who reads cross slope to 0.5 % "
        f"({_pm(b1h)} pp). At {seats[-1]} mrad of seating noise it is {_standing(worse_seat)} him ({_pm(worse_seat)} pp), and at "
        f"{worse_tr_key} deg of transfer error {_standing(worse_tr)} him ({_pm(worse_tr)} pp, sweep subset) (sections 1, 4).",
        f"2. The median miss of a single placement exceeds the hole radius from {_first_beyond_hole(summary, 'B1') or 'no length tested'} m "
        f"on (undulating greens, all lengths: {_cm(_seat(summary)['B1']['by_class']['undulating']['median_miss'])} cm); the limit is "
        "the green, not the sensor (sections 1, 8).",
        f"3. The flag-base height does not improve the line ({_pm(paired['B1_vs_B0'], 'd_mean_miss', 100.0, 2)} cm of mean miss), "
        f"is hidden on {_pct(flag_d[mid6]['base_hidden'])} % of the putts at {mid6} m and {_pct(flag_d[dk[-1]]['base_hidden'])} % at "
        f"{dk[-1]} m, and its one-sided form on crowned lines is no better than treating the sight line as the base "
        f"({_pm(sw['flag_base_paired']['B1_blind_vs_informed'])} pp for doing so) (sections 7, 11).",
        f"4. The turf-horizon path: with realistic surrounds {real_words[verdict_sign(ht['realistic']['anchored']['all']['verdict'])]} "
        f"at the default extent of the terrain model and {real_words[verdict_sign(dom_last['verdict'])]} at the largest one; with "
        f"greenside mounds {real_words[verdict_sign(ht['mounded']['anchored']['all']['verdict'])]}. An earlier, more favourable "
        "result was an artefact of the optimiser. It is off by default (section 5).",
        f"5. Stick-height ranging is available on only about half of the long putts; the fused range at {dk[-1]} m is "
        f"{_pct(diag['range'][dk[-1]]['fused_rms'], 1)} % RMS, not the 2-3 % of the design spec, and a stereo calibration drift "
        f"of +0.1 px shifts it by {_signed(100 * sy['disparity bias +0.1 px']['range'][mid]['fused_bias'], 1)} % at {mid} m "
        f"against a random error of {_pct(sy['baseline']['range'][mid]['fused_rms'], 1)} % (section 6).",
        f"6. On double-breaking putts a Quick Read misses by a median of {_cm(sub['B1'].get('median_miss'))} cm against "
        f"{_cm(sub['STRAIGHT'].get('median_miss'))} cm for aiming straight, and nothing in a single read reveals that it is on such "
        "a putt (section 12).",
        "7. The Survey's plane-plus-curvature model handles the cross slope well but not the pace on long crowned putts (section 12).",
        "8. The confidence score is calibrated on average but carries almost no information beyond putt length and mode (section 12).",
        "9. Pace accuracy is set by the golfer's green-speed entry, not by anything the device senses (sections 8, 11).",
        f"10. Numerics: the aim solver could not solve the fitted patch in a handful of reads and fell back to the secant "
        f"plane or a best-effort iterate (counts in section 12); the true-surface oracle solved "
        f"{meta['n_putts_main'] - diag['oracle_not_solved']} of {meta['n_putts_main']} putts. Of {n_rolls} evaluation rolls at the "
        f"nominal seating level, {n_time} were still moving at the 30 s time limit or the step budget and {n_oob} left the "
        "modelled surface (neither holed nor at rest; they are counted as misses, not dropped; section 14.3).",
    ]
    return "\n".join(out)


def _numerics_text(summary) -> str:
    diag = summary["main"]["diagnostics"]
    rs = diag["roll_status"]
    bad = {k: v for k, v in rs.items() if v["max_time"] + v["out_of_bounds"] + v["max_time_human"] + v["out_of_bounds_human"] > 0}
    n_rolls = sum(v["n"] + v["n_human"] for v in rs.values())
    lines = [
        "The roll kernel is classical RK4 with a 0.02 s step. Near the stop the step is shortened to half the predicted "
        "time-to-stop and to 0.5 x speed / a_r; the second rule is needed because the friction term makes the velocity "
        "component across the drive decay at the rate a_r / speed, which explicit RK4 follows stably only for "
        "h a_r / speed < 2.785. Without it a ball stopping with a slope steeper than about 0.85 of the critical slope crept "
        "at 0.36 x drive x dt until the time limit (5 cm error at 0.95 of critical); with it the rest position on slopes "
        "up to 0.99 of critical agrees with an implicit reference integrator to 2e-7 m (tests). A roll may take at most "
        "4 x t_max / dt steps.",
        "",
        "The aim solver treats a trial ball that crosses the infinite hole line more than 1 m + 0.5 D to the side as not "
        "having reached the hole. Without this rule it missed regular solutions on long, strongly twisted patches. Solver "
        "failures that remain occur where the slope-plus-grain drive near the path approaches or exceeds a_r; most are "
        "physical (no putt with the asked pace exists), but the solver is a nested bracketing search and can also fail to "
        "find a solution that exists.",
        "",
        f"Every evaluation roll's end status is recorded. At the nominal seating level {n_rolls} rolls were made; rolls that "
        "were neither holed nor at rest at the end: "
        + ("none." if not bad else "; ".join(
            f"{k}: {v['max_time'] + v['max_time_human']} still moving, {v['out_of_bounds'] + v['out_of_bounds_human']} off the modelled surface"
            for k, v in bad.items()) + ". \"Still moving\" means at the 30 s time limit or at the step budget: balls running "
            "away down a tier face, or creeping on a slope within a fraction of a percent of the critical one (checked "
            "case by case for the STRAIGHT rolls of the default run: with a longer time limit and a ten times finer step "
            "they stop within 1 mm of the same place). They count as misses with the lateral miss they had; nothing is dropped."),
    ]
    return "\n".join(lines)


_NARRATIVE = {
    "HEADLINE_TEXT": _headline_text,
    "SENSOR_TEXT": _sensor_text,
    "SEAT_TEXT": _seat_text,
    "TRANSFER_TEXT": _transfer_text,
    "RELIEF_TEXT": _relief_text,
    "HORIZON_TEXT": _horizon_text,
    "RANGE_TEXT": _range_text,
    "FLAG_TEXT": _flag_text,
    "BUDGET_TEXT": _budget_text,
    "EXEC_TEXT": _exec_text,
    "BEARING_TEXT": _bearing_text,
    "SWEEP_TEXT": _sweep_text,
    "FUSION_TEXT": _fusion_text,
    "LIMITS_TEXT": _limits_text,
    "NUMERICS_TEXT": _numerics_text,
}


def render(summary: dict, figs: Sequence[str]) -> str:
    """The text of ``REPORT.md``."""
    meta = summary["meta"]
    dk = _dkeys(summary)
    nom = _seat(summary)
    diag = summary["main"]["diagnostics"]
    sw = summary["sweeps"]
    seats = [f"{s:g}" for s in meta["seat_levels_mrad"]]
    nseat = f"{meta['nominal_seat_mrad']:g}"
    cam = meta["camera"]
    rt = meta["runtime_s"]
    ec = meta["estimator_config"]
    fig = {os.path.splitext(f)[0].split("_", 1)[0]: f for f in figs}

    def cell(method, d, key, seat=None):
        return _seat(summary, seat)[method]["by_distance"][d][key]

    L: List[str] = []
    add = L.append

    # ------------------------------------------------------------------ title
    add("# GreenLine simulation report")
    add("")
    add(
        "Generated by `python -m greenline_sim.montecarlo` from the Python reference in `sim/greenline_sim`. "
        "Every number below is read from `results/summary.json`; the wording of the verdicts follows fixed rules applied "
        "to those numbers. Nothing here is a measurement of hardware: it is a simulation of the GL-1 design (hardware "
        "revision C) on synthetic greens, and several decisive inputs are estimates (section 13)."
    )
    add("")
    add(
        f"**Size of the run.** {meta['n_putts_main']} putts in the main experiment: {len(meta['distances'])} putt lengths x "
        f"{len(meta['classes'])} green classes x {meta['n_putts_per_cell']} seeded greens, i.e. N = {meta['n_putts_per_cell']} "
        f"per (length, class) cell and N = {meta['n_putts_per_cell'] * len(meta['classes'])} per length. Each putt is evaluated "
        f"for every method at {len(seats)} seating-noise levels, once with a perfect stroke and {meta['n_exec']} times with "
        f"human execution noise ({meta['sigma_dir_deg']:g} deg direction, {100 * meta['sigma_speed']:g} % speed, 1 sigma). "
        f"The sensitivity sweeps use the first {meta['n_putts_sweep']} putts; variant comparisons that are reported for the "
        f"perfect stroke only are rolled once per putt. Master seed {meta['master_seed']}. "
        f"Runtime {rt['total']:.0f} s wall clock ({rt['main']:.0f} s main, {rt['sweeps']:.0f} s sweeps) and {rt['cpu']:.0f} s of "
        f"CPU time on {rt['n_cpu']} cores, with {meta['numba']}; the load average of the machine when the run started was "
        f"{rt['load_average_at_start']:.1f}"
        + (" (it was shared with other jobs, so the wall-clock figure is inflated; on a machine of its own the run cannot "
           "take longer than its CPU time)" if rt["load_average_at_start"] > 1.5 else "")
        + ". "
        f"{meta['n_skipped']} (green, length) pairs had no legal putt and were skipped."
    )
    add("")
    add(
        f"**Statistical resolution.** With N = {meta['n_putts_per_cell'] * len(meta['classes'])} per length a make probability "
        f"near 50 % has a standard error of about {100 * 0.5 / math.sqrt(meta['n_putts_per_cell'] * len(meta['classes'])):.1f} "
        f"percentage points (pp); per (length, class) cell it is about {100 * 0.5 / math.sqrt(meta['n_putts_per_cell']):.0f} pp, "
        "so single cells of the appendix tables are indicative only. Method comparisons are paired (same greens, same noise "
        "draws) and are quoted with 95 % intervals; a difference is called real only beyond 2 standard errors."
    )
    add("")
    add(
        "**Shipping configuration - the default of every table unless it says otherwise.** (1) The grain reading is NOT "
        f"used (`use_grain = {ec['use_grain']}`): the design specification ships the grain sensor disabled. The human baselines "
        f"solve without grain too (`human_grain = \"{meta['human_grain']}\"`). (2) The golfer follows the LINE on the puck: "
        f"its direction is quantised by the 1-bit display in steps of {meta['display_step_deg']:.2f} deg and transferred to "
        f"the ball with a further {meta['sigma_transfer_deg']:g} deg (1 sigma, an estimate). \"Perfect stroke\" for a device "
        "mode therefore means a perfect stroke along the line the golfer took from the display. (3) Firmware default "
        f"method: `{meta['default_method']}`."
    )
    add("")

    # ------------------------------------------------------------------ 1 headline
    add("## 1. Headline")
    add("")
    add(f"All putt lengths pooled, seating noise {nseat} mrad, shipping configuration:")
    add("")
    add(_headline(summary))
    add("")
    add("@@HEADLINE_TEXT@@")
    add("")
    add(f"![Median lateral miss by distance]({fig['fig1']})")
    add("")
    add(f"![Make probability]({fig['fig2']})")
    add("")

    # ------------------------------------------------------------------ 2 setup
    add("## 2. What was simulated")
    add("")
    add(
        f"**Hardware (preset {cam['name']}, revision C).** Stereo pair with f = {cam['f_px']:g} px and baseline "
        f"{1e3 * cam['baseline']:g} mm, optical axis {1e3 * cam['h_cam']:g} mm above the base plane (the puck sinks an unknown 0-"
        f"{1e3 * meta['sensor_params']['sink_max']:g} mm into the canopy), horizontal field ±{cam['half_fov_h_deg']:g} deg, "
        f"usable upward field {cam['up_fov_deg']:g} deg. The device measures: puck tilt; flagstick bearing, stereo disparity, "
        "elevation of the lowest visible point of the stick and, when in the field, of its top; the turf-horizon elevation at "
        f"{meta['sensor_params']['n_horizon']} azimuths; grain (unused by default); and takes the green speed from the golfer. "
        "It cannot see the surface between ball and hole in a range-resolved way, and nothing in the estimator pretends it "
        f"can: at lens height h the ground at distance d subtends h / d^2 rad per metre ({1e3 * cam['h_cam'] / 9.0:.1f} mrad per "
        f"metre at 3 m, {cam['f_px'] * cam['h_cam'] / 9.0:.1f} px), so the whole green collapses onto the horizon line."
    )
    add("")
    add("**Methods.**")
    add("")
    add(_table(
        ["Name", "What it is", "Inputs"],
        [
            ["STRAIGHT", "aim at the flag, flat-green pace", "the golfer aims at the hole himself; entered Stimp, camera range"],
            ["B0", "plane from one tilt reading (what a digital-level ball marker gives)", "+ puck tilt"],
            ["B1", "Quick Read: MAP fit of a quadratic patch (convex problem)", "+ flag-base height (or a one-sided bound when the base is hidden)"],
            ["B2", "B1 + turf horizon, anchored: slopes at the ball and along-line curvature held at the B1 solution, twist and cross curvature from the horizon", "+ horizon profile"],
            ["B0S", "Precision Read: B1 with a 180-degree spin-and-reread", "two seatings averaged, device bias cancelled"],
            ["SURVEY2 / SURVEY3", "Survey: drops at the ball, the midpoint (and 1 m short of the hole)", "each drop: tilt, own range and bearing, own hole height"],
            ["FLAGOUT", "flag-out fallback, tilt only", "visor pointed by hand (1.5 deg), dialled distance (10 %)"],
            ["HUMAN05 / HUMAN10", "golfer who reads the path-average cross slope with 0.5 % / 1 % error", "true hole height, bearing and distance; the same entered Stimp as the device; no grain; aims without the display"],
            ["ORACLE_SLOPE", "true surface, but the entered Stimp and the device's grain knowledge (none)", "isolates slope reading from speed and grain knowledge"],
            ["ORACLE", "true surface, true Stimp, true grain", "upper bound"],
        ],
    ))
    add("")
    add(
        "All methods aim for the same target pace (the ball would roll 0.30 m past the hole on a flat green). A camera read "
        "that does not find the flag is retried as a flag-out read, and every device mode then works from that. The "
        "estimator's assumed noise levels are firmware constants and stay at their nominal values in every sweep, as they "
        "would in a shipped device."
    )
    add("")
    add(
        "**Greens.** Four classes (planar, gentle, undulating, tiered), overall tilt 0.5-3 %, undulation correlation length "
        "4-8 m (no relief below about 15 m wavelength: section 4.3), hole where the local slope is at most 3 %, green edge "
        "9-16 m from the centre, collar +8 mm, rough +40 mm, surround terrain beyond the collar with a mean radial slope of "
        "-8 % to +2 %, modelled out to 24 m from the centre. True Stimp ~ N(10, 1.2), grain strong on 35 % of greens. The ball "
        "rolls with `dv/dt = -a_r v_hat - (5/7) G grad z + kappa a_r g_hat`."
    )
    add("")

    # ------------------------------------------------------------------ 3 sensors and main tables
    add(f"## 3. What each sensor buys, and the results at the nominal seating noise ({nseat} mrad)")
    add("")
    add("**What each sensor buys** (all lengths pooled; each row adds one measurement to the row above):")
    add("")
    add(_sensor_table(summary))
    add("")
    add("@@SENSOR_TEXT@@")
    add("")
    add("The same chain by putt length (median lateral miss [cm] / putts holed with a perfect stroke [%]):")
    add("")
    rows = []
    for d in dk:
        rows.append([f"{d} m"] + [f"{_cm(nom[m]['by_distance'][d]['median_miss'])} / {_pct(nom[m]['by_distance'][d]['make_perfect'])}" for m in SENSOR_CHAIN])
    add(_table(["Putt"] + list(SENSOR_CHAIN), rows))
    add("")
    add("**All methods.** Median absolute lateral miss at the hole, perfect stroke [cm]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "median_miss", _cm))
    add("")
    add("90th percentile of the lateral miss, perfect stroke [cm]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "p90_miss", _cm))
    add("")
    add("Make probability with a perfect stroke [%]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "make_perfect", _pct))
    add("")
    add(f"Make probability with human execution noise ({meta['sigma_dir_deg']:g} deg, {100 * meta['sigma_speed']:g} %) [%]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "make_human", lambda v: _pct(v, 1)))
    add("")
    add("By green class, all lengths pooled (median miss [cm] / make probability with a perfect stroke [%]):")
    add("")
    rows = []
    for m in ALL_METHODS:
        rows.append([m] + [f"{_cm(nom[m]['by_class'][c]['median_miss'])} / {_pct(nom[m]['by_class'][c]['make_perfect'])}" for c in meta["classes"]])
    add(_table(["Method"] + list(meta["classes"]), rows))
    add("")
    add(f"![Median miss by green class]({fig['fig8']})")
    add("")
    add("The per-length, per-class tables are in the appendix (section 14).")
    add("")

    # ------------------------------------------------------------------ 4 unmeasured inputs
    add("## 4. Seating noise, aim transfer and the smoothness of the green: the inputs nobody has measured")
    add("")
    add(f"![Make probability against the three unmeasured inputs]({fig['fig9']})")
    add("")
    add("### 4.1 Seating noise")
    add("")
    add(
        "How a 46 mm puck seats on turf has not been measured; 2-5 mrad per placement is an estimate. Every method was "
        "therefore run at a TRUE seating noise of " + ", ".join(seats) + " mrad per axis (the estimator keeps assuming 2.5). "
        "The two human baselines, STRAIGHT and the oracles do not use the tilt and are identical in all three blocks."
    )
    add("")
    for s in seats:
        t = _seat(summary, s)
        add(f"**Seating noise {s} mrad** - median lateral miss [cm]:")
        add("")
        add(_by_distance_table(t, ALL_METHODS, dk, "median_miss", _cm))
        add("")
        add(f"Seating noise {s} mrad - make probability, perfect stroke [%]:")
        add("")
        add(_by_distance_table(t, ALL_METHODS, dk, "make_perfect", _pct))
        add("")
        add(f"Seating noise {s} mrad - make probability, human execution [%]:")
        add("")
        add(_by_distance_table(t, ALL_METHODS, dk, "make_human", lambda v: _pct(v, 1)))
        add("")
    add(f"![Seating-noise sensitivity]({fig['fig3']})")
    add("")
    ext = sw["seating_ext_mrad"]
    add(f"Beyond the main range (sweep subset, {meta['n_putts_sweep']} putts; make probability, perfect stroke / human execution [%]; "
        f"0.5 % reader {_mk(sw['baseline'], 'HUMAN05')} / {_mk(sw['baseline'], 'HUMAN05', 'make_human')}, "
        f"1 % reader {_mk(sw['baseline'], 'HUMAN10')} / {_mk(sw['baseline'], 'HUMAN10', 'make_human')}):")
    add("")
    add(_table(["Seating noise"] + list(next(iter(ext.values()))),
               [[f"{k} mrad"] + [f"{_mk(v, m)} / {_mk(v, m, 'make_human')}" for m in v] for k, v in ext.items()]))
    add("")
    add("@@SEAT_TEXT@@")
    add("")
    add("### 4.2 Aim transfer: reading the line off the puck")
    add("")
    tr = sw["transfer_deg"]
    tp = sw["transfer_vs_human"]
    rows = []
    for k, v in tr.items():
        rows.append([f"{k} deg" if k.replace(".", "", 1).isdigit() else k]
                    + [f"{_mk(v, m)} / {_mk(v, m, 'make_human')}" for m in ("B1", "B0S", "SURVEY3")]
                    + [f"{_pm(tp[k]['B1_vs_HUMAN05'])} / {_pm(tp[k]['B1_vs_HUMAN05'], 'd_make_human')}",
                       f"{_pm(tp[k]['SURVEY3_vs_HUMAN05'])} / {_pm(tp[k]['SURVEY3_vs_HUMAN05'], 'd_make_human')}"])
    add(f"Sweep subset; make probability, perfect stroke / human execution [%]. The human baselines do not use the display "
        f"(0.5 % reader {_mk(sw['baseline'], 'HUMAN05')} / {_mk(sw['baseline'], 'HUMAN05', 'make_human')} in every row):")
    add("")
    add(_table(["Transfer error (1 sigma)", "B1", "B0S", "SURVEY3", "B1 minus 0.5 % reader [pp]", "SURVEY3 minus 0.5 % reader [pp]"], rows))
    add("")
    add("@@TRANSFER_TEXT@@")
    add("")
    add("### 4.3 Metre-scale relief of the green")
    add("")
    rl = sw["relief_mm"]
    rp = sw["relief_paired"]
    rows = []
    for k, v in rl.items():
        rows.append([f"{k} mm", _mrad(sw["relief_added_slope"][k])]
                    + [f"{_mk(v, m)} / {_mk(v, m, 'make_human')}" for m in ("B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "STRAIGHT")]
                    + [_pm(rp[k]["B1_vs_HUMAN05"]), _pm(rp[k]["SURVEY3_vs_B1"])])
    add("Sweep subset; make probability, perfect stroke / human execution [%]:")
    add("")
    add(_table(["Relief RMS", "added slope per axis [mrad]", "B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "STRAIGHT",
                "B1 minus 0.5 % reader [pp]", "SURVEY3 minus B1 [pp]"], rows))
    add("")
    add("@@RELIEF_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 5 horizon
    add("## 5. Is the turf horizon usable? (B2 against B1)")
    add("")
    add(
        "Reviewers of the concept expected the turf-horizon path to cross slope to fail in practice because the silhouette is "
        "formed by collar, rough and surrounds rather than by the putting surface. This was tested, not assumed. B2 differs "
        "from B1 only by the horizon residuals, and the same putts were re-measured with four versions of what lies beyond "
        "the putting surface: nothing (the camera sees the smooth continuation of the green - optimistic), the collar and "
        "rough canopy steps only, the generator's default surrounds (realistic as modelled), and surrounds with mounds and "
        "hollows of 0.2 m RMS that are independent of the green (pessimistic). Four forms of the horizon fit are shown, "
        "because the answer depends on the form."
    )
    add("")
    add(_horizon_tables(summary))
    add("")
    add(f"![Horizon test]({fig['fig4']})")
    add("")
    add(_horizon_verdict(summary))
    add("")
    add("@@HORIZON_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 6 range
    add("## 6. Range to the flag: stereo, stick height, fused")
    add("")
    rng = diag["range"]
    fh = sw["range_first_hole"]
    rows = []
    for d in dk:
        r = rng[d]
        rows.append([
            f"{d} m", _pct(r["stereo_rms"], 1), _pct(r["stereo_predicted"], 1), _pct(r["mono_available"]), _pct(r["mono_rms"], 1),
            _pct(r["fused_rms"], 1), _pct(fh[d]["mono_rms"], 1), _pct(fh[d]["fused_rms"], 1),
        ])
    add(_table(
        ["Putt", "stereo only RMS [%]", "stereo predicted D sigma_disp / (f b) [%]", "stick-height range available [% of reads]",
         "stick height only RMS [%] (learned, 2 %)", "fused RMS [%] (learned)", "stick height only RMS [%] (first hole, 7 % prior)",
         "fused RMS [%] (first hole)"], rows))
    add("")
    add("The first-hole columns come from the sweep subset. Camera presets (sweep subset, fused RMS range error [%] / flag found [%]):")
    add("")
    rows = []
    for name, tab in sw["camera_range"].items():
        rows.append([name] + [_pct(tab[d]["fused_rms"], 1) for d in dk] + [_pct(sw["camera_found"][name], 1)])
    add(_table(["Preset"] + [f"{d} m" for d in dk] + ["flag found, all lengths [%]"], rows))
    add("")
    add("Stereo calibration drift (sweep subset; a constant disparity error on every read; fused range, signed mean error / "
        "RMS error [%]):")
    add("")
    sy = sw["systematics"]
    rows = []
    for label, v in sy.items():
        if label != "baseline" and not label.startswith("disparity"):
            continue
        rows.append([label] + [f"{_signed(100 * v['range'][d]['fused_bias'], 1)} / {_pct(v['range'][d]['fused_rms'], 1)}" for d in dk[2:]]
                    + [_pct(v["B1"]["overall"]["make_perfect"], 1), _pct(v["B1"]["overall"]["short"]),
                       _pm(v["vs_baseline"]) if label != "baseline" else "-"])
    add(_table(["Variant"] + [f"{d} m" for d in dk[2:]] + ["B1 holed [%]", "B1 short of the hole [%]", "B1 change [pp]"], rows))
    add("")
    add(f"![Range error]({fig['fig5']})")
    add("")
    add("@@RANGE_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 7 flag
    add("## 7. The flagstick: detection and the hidden base")
    add("")
    fl = diag["flag"]
    rows = []
    for d in dk:
        r = fl["by_distance"][d]
        rows.append([f"{d} m", _pct(r["found"], 1), _pct(r["in_fov"], 1), _pct(r["base_hidden"]), f"{1e3 * r['hidden_height_median']:.0f}"]
                    + [_pct(fl["hidden_by_distance_class"][f"{d}|{c}"]) for c in meta["classes"]])
    add(_table(["Putt", "flag found [%]", "flag inside the field [%]", "base hidden [%]", "median hidden stick length when hidden [mm]"]
               + [f"hidden, {c} [%]" for c in meta["classes"]], rows))
    add("")
    add("@@FLAG_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 8 error budget
    add("## 8. Error budget of the read")
    add("")
    se_tab = diag["slope_error"]
    meths = [m for m in ("B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3") if m in se_tab[dk[0]]["cross"]]
    add("RMS error of the mean cross slope along the line (the quantity that sets the break) [mrad]:")
    add("")
    rows = [[f"{d} m", _mrad(se_tab[d]["mean_cross_rms"]), _mrad(se_tab[d]["representativeness"])] + [_mrad(se_tab[d]["cross"][m]) for m in meths] for d in dk]
    add(_table(["Putt", "RMS of the true mean cross slope", "true slope at the ball minus true path average"] + meths, rows))
    add("")
    add("RMS error of the mean slope along the line (which sets the pace) [mrad], base visible / base hidden from the ball:")
    add("")
    rows = [[f"{d} m"] + [f"{_mrad(se_tab[d]['along_base_visible'][m])} / {_mrad(se_tab[d]['along_base_hidden'][m])}" for m in meths] for d in dk]
    add(_table(["Putt"] + meths, rows))
    add("")
    add("RMS error of the FITTED patch slopes at the ball against the true slope there, along the line / across it [mrad] "
        "(the displayed slope and fall line are always the tilt reading, whatever the fit):")
    add("")
    meths_ball = [m for m in ("B0", "B1", "B2", "B2J", "B0S", "SURVEY2", "SURVEY3") if m in se_tab[dk[0]]["along_at_ball"]]
    rows = [[f"{d} m"] + [f"{_mrad(se_tab[d]['along_at_ball'][m])} / {_mrad(se_tab[d]['cross_at_ball'][m])}" for m in meths_ball] for d in dk]
    add(_table(["Putt"] + [m if m != "B2J" else "B2J (joint horizon fit)" for m in meths_ball], rows))
    add("")
    add("Pace: median absolute error of the roll-out past the hole against the 0.30 m target [cm] (perfect stroke):")
    add("")
    add(_by_distance_table(nom, ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT", "HUMAN05", "ORACLE_SLOPE", "ORACLE"), dk, "median_pace_err", lambda v: _cm(v, 0)))
    add("")
    add("Putts that stop short of the hole with a perfect stroke [%]:")
    add("")
    add(_by_distance_table(nom, ("STRAIGHT", "B0", "B1", "SURVEY3", "HUMAN05", "ORACLE_SLOPE", "ORACLE"), dk, "short", _pct))
    add("")
    add(f"![Cross-slope error]({fig['fig6']})")
    add("")
    add("@@BUDGET_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 9 sensing vs execution
    add("## 9. Sensing against human execution")
    add("")
    rows = []
    for d in dk:
        rows.append([
            f"{d} m", _pct(cell("ORACLE", d, "make_human"), 1), _pct(cell("ORACLE_SLOPE", d, "make_human"), 1),
            _pct(cell("SURVEY3", d, "make_human"), 1), _pct(cell("B0S", d, "make_human"), 1), _pct(cell("B1", d, "make_human"), 1),
            _pct(cell("HUMAN05", d, "make_human"), 1), _pct(cell("HUMAN10", d, "make_human"), 1), _pct(cell("STRAIGHT", d, "make_human"), 1),
            _cm(cell("ORACLE", d, "median_miss_human")), _cm(cell("B1", d, "median_miss")), _cm(cell("B1", d, "median_miss_human")),
        ])
    add(_table(
        ["Putt", "ORACLE", "ORACLE_SLOPE", "SURVEY3", "B0S", "B1", "HUMAN05", "HUMAN10", "STRAIGHT",
         "median miss, execution only (ORACLE) [cm]", "median miss, read only (B1) [cm]", "median miss, read + execution (B1) [cm]"], rows))
    add("")
    add(f"Columns 2-9: make probability with human execution at {meta['sigma_dir_deg']:g} deg / {100 * meta['sigma_speed']:g} % [%].")
    add("")
    add("@@EXEC_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 10 bearing
    add("## 10. Bearing and distance: the flag-out fallback")
    add("")
    add(_by_distance_table(nom, ("B0", "FLAGOUT", "FLAGOUT_CUPS"), dk, "median_miss", _cm))
    add("")
    add("Median lateral miss [cm] above; make probability with a perfect stroke [%] below (FLAGOUT_CUPS: the same reads "
        "under the break-in-cups use model).")
    add("")
    add(_by_distance_table(nom, ("B0", "FLAGOUT", "FLAGOUT_CUPS"), dk, "make_perfect", _pct))
    add("")
    add("Bearing x distance (sweep subset, tilt-only plane, perfect stroke):")
    add("")
    fo = sw["flagout_2x2"]
    rows = [[k, _pct(v["FLAGOUT"]["overall"]["make_perfect"], 1), _cm(v["FLAGOUT"]["overall"]["median_miss"]),
             _cm(v["FLAGOUT"]["overall"]["median_pace_err"], 0), _pct(v["FLAGOUT"]["overall"]["short"])] for k, v in fo.items()]
    add(_table(["Variant", "holed [%]", "median miss [cm]", "median pace error [cm]", "short of the hole [%]"], rows))
    add("")
    fp = sw["flagout_2x2_paired"]
    add(_table(["Paired difference", "Δ make prob. [pp]", "Δ mean miss [cm]"],
               [[k, _pm(v), _pm(v, "d_mean_miss", 100.0, 2)] for k, v in fp.items()]))
    add("")
    add("@@BEARING_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 11 sweeps
    add(f"## 11. Other sensitivity sweeps ({meta['n_putts_sweep']} putts, seating noise {nseat} mrad)")
    add("")
    add("All rows of one table use the same putts and the same noise draws. \"pace err\" is the median absolute pace error; "
        "\"make\" is with a perfect stroke.")
    add("")
    add("**Camera preset.** The legacy presets also differ from GL1 in baseline (34 mm), field of view (±40 deg) and lens height (4.5 mm).")
    add("")
    add(_sweep_table("Preset", sw["camera"], ("B1",), dk))
    add("")
    add("**Lens height** (fraction of reads with the base hidden in the last column):")
    add("")
    rows = []
    for label, tables in sw["h_cam_mm"].items():
        for r in _sweep_rows({label + " mm": tables}, ("B1",), dk):
            rows.append(r + [_pct(tables["base_hidden"])])
    add(_table(["Lens height", "Method"] + [f"miss {d} m" for d in dk] + ["miss all [cm]", "make all [%]", "pace err [cm]", "base hidden [%]"], rows))
    add("")
    add("**Flag-base height.**")
    add("")
    add(_sweep_table("Variant", sw["flag_base"], ("B1", "B2"), dk))
    add("")
    add("**Error of the entered green speed** (1 sigma, % of Stimp):")
    add("")
    add(_sweep_table("Stimp error [%]", sw["stimp_error_pct"], ("B1", "ORACLE_SLOPE"), dk))
    add("")
    add("**Grain sensor** (make probability with a perfect stroke [%]; the first row is the shipping default):")
    add("")
    gr_ = sw["grain"]
    gv = sw["grain_vs_off"]
    gs = sw["grain_strong_greens"]
    rows = []
    for k, v in gr_.items():
        rows.append([k] + [_mk(v, m) if m in v else "-" for m in ("B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10")]
                    + [_pct(gs[k]["make_perfect"], 1) if k in gs else "-", _pm(gv[k]) if k in gv else "-"])
    add(_table(["Variant", "B1", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "B1 on strongly grained greens", "B1 minus B1 without sensor [pp]"], rows))
    add("")
    add("In the second row the human baselines are given the same grain reading as the device; in the first row neither has any.")
    add("")
    add("**Precision Read when the two seatings are correlated** (0 = independent, 1 = the spin only cancels the device bias):")
    add("")
    add(_sweep_table("Correlation", sw["spin_seat_correlation"], ("B1", "B0S"), dk))
    add("")
    add("**Survey: lateral placement error of the drops** (1 sigma, off the true ball-to-hole line):")
    add("")
    lat = sw["survey_lateral_m"]
    lp = sw["survey_lateral_paired"]
    add(_table(["Lateral sigma", "SURVEY2 holed [%]", "SURVEY3 holed [%]", "SURVEY3 minus B1 [pp]", "SURVEY2 minus B1 [pp]",
                "SURVEY3 holed at 3 m [%]"],
               [[f"{k} m", _mk(v, "SURVEY2"), _mk(v, "SURVEY3"), _pm(lp[k]["SURVEY3_vs_B1"]), _pm(lp[k]["SURVEY2_vs_B1"]),
                 _pct(v["SURVEY3"]["by_distance"][_pick(dk, ("3",))[0]]["make_perfect"], 1)] for k, v in lat.items()]))
    add("")
    add("**Survey: allowance for the slope field not being plane-plus-curvature** (`sigma_field`):")
    add("")
    add(_sweep_table("sigma_field [mrad]", sw["survey_sigma_field_mrad"], ("SURVEY2", "SURVEY3"), dk))
    add("")
    add("**Seating outliers.**")
    add("")
    add(_level_table("Variant", sw["seating_outliers"], ("B1", "B0S", "SURVEY3")))
    add("")
    add("**Systematic and out-of-range sensor errors** (B1):")
    add("")
    far = dk[-1]
    mid = _pick(dk, ("6",))[0]
    rows = []
    for label, v in sy.items():
        rows.append([label, _pct(v["B1"]["overall"]["make_perfect"], 1), _pm(v["vs_baseline"]) if label != "baseline" else "-",
                     _cm(v["B1"]["overall"]["median_miss"]), _cm(v["B1"]["overall"]["median_pace_err"], 0), _pct(v["found"], 1),
                     _pct(v["base_hidden"], 1), f"{_mrad(v['along_base_visible'][mid], 2)} / {_mrad(v['along_base_visible'][far], 2)}"])
    add(_table(["Variant", "holed [%]", "change [pp]", "median miss [cm]", "median pace error [cm]", "flag found [%]",
                "base hidden [%]", f"along-line slope error, base visible, {mid} m / {far} m [mrad]"], rows))
    add("")
    add("@@SWEEP_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 12 where it helps
    add("## 12. Where fusion helps, where it does not, and what the confidence score is worth")
    add("")
    sub = diag["subsets"]
    cols = ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05", "HUMAN10")
    rows = []
    for label, entry in sub.items():
        n = entry["B1"].get("n", 0)
        if n == 0:
            continue
        rows.append([label, str(n)] + [f"{_cm(entry[m]['median_miss'])} / {_pct(entry[m]['make_perfect'])}" for m in cols])
    add("Median miss [cm] / make probability with a perfect stroke [%] on subsets of the putts:")
    add("")
    add(_table(["Subset", "N"] + list(cols), rows))
    add("")
    dbf = diag["double_break_fraction"]
    add("Share of putts with a double break (cross slope changes sign along the line with at least 0.3 % on both sides): "
        + ", ".join(f"{d} m {_pct(dbf[d])} %" for d in dk) + ".")
    add("")
    conf = diag["confidence"]
    add("Confidence score against outcome (perfect stroke; \"within\" = the line passes within the hole radius of the centre):")
    add("")
    rows = []
    for m, v in conf.items():
        rows.append([m, f"{v['mean_confidence']:.3f}", f"{v['within_hole']:.3f}", f"{v['z_rms']:.2f}", f"{v['spearman_pooled']:.2f}",
                     f"{v['spearman_minus_distance']:.2f}", f"{v['spearman_within_length']:.2f}"]
                    + [f"{v['by_distance'][d]['mean_confidence']:.2f} / {v['by_distance'][d]['within_hole']:.2f}" for d in dk])
    add(_table(["Mode", "mean score", "fraction within", "RMS (cross-slope error / claimed sigma)",
                "rank correlation of score with |miss|, all putts", "same for minus the distance alone",
                "rank correlation inside one putt length (mean)"] + [f"score / within at {d} m" for d in dk], rows))
    add("")
    cal = {m: v["bins"] for m, v in conf.items()}
    all_edges = sorted({(r["lo"], r["hi"]) for m in cal for r in cal[m]})
    rows = []
    for lo, hi in all_edges:
        row = [f"{lo:.2f}-{hi:.2f}"]
        for m in ("B1", "B0S", "SURVEY3", "B2"):
            hit = [r for r in cal[m] if r["lo"] == lo]
            row.append(f"{hit[0]['mean_confidence']:.2f} -> {hit[0]['within_hole']:.2f} (n={hit[0]['n']})" if hit else "-")
        rows.append(row)
    add(_table(["Confidence bin", "B1: mean score -> fraction within", "B0S", "SURVEY3", "B2"], rows))
    add("")
    add(f"![Confidence calibration]({fig['fig7']})")
    add("")
    add("How the aim was obtained (number of reads solved on the fitted patch / on its secant plane / best effort / straight): "
        + "; ".join(f"{m} {'/'.join(str(v) for v in c)}" for m, c in diag["aim_sources"].items() if m in ("B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT")) + ".")
    add("")
    add("@@FUSION_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 13 limitations
    add("## 13. Limitations and honest caveats")
    add("")
    add("@@LIMITS_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 14 appendix
    add("## 14. Appendix")
    add("")
    add("### 14.1 Per length and class")
    add("")
    cols = ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05", "HUMAN10", "ORACLE")
    for key, title, fmt in (
        ("median_miss", "Median lateral miss, perfect stroke [cm]", _cm),
        ("p90_miss", "90th percentile of the lateral miss, perfect stroke [cm]", _cm),
        ("make_perfect", "Make probability, perfect stroke [%]", _pct),
        ("make_human", "Make probability, human execution [%]", _pct),
    ):
        add(f"{title} (N = {meta['n_putts_per_cell']} per row):")
        add("")
        rows = []
        for d in dk:
            for c in meta["classes"]:
                rows.append([f"{d} m", c] + [fmt(nom[m]["by_distance_class"][f"{d}|{c}"].get(key)) for m in cols])
        add(_table(["Putt", "Class"] + list(cols), rows))
        add("")
    add("### 14.2 Closed-form check of the physics")
    add("")
    add("Dying putt (`past = 0`) on a plane with pure cross slope `s`; small-slope theory `phi = (5/14) G s / a_r`:")
    add("")
    add(_closed_form())
    add("")
    add("### 14.3 Numerics: the roll kernel, the solver and the roll statuses")
    add("")
    add("@@NUMERICS_TEXT@@")
    add("")
    add("### 14.4 Reproducing")
    add("")
    add("```")
    add("cd sim")
    add("python -m pytest -q                 # test-suite")
    add(f"python -m greenline_sim.montecarlo  # this report, summary.json, plots, reference vectors (about {rt['cpu'] / 60.0:.0f} min of CPU time)")
    add("python -m greenline_sim.report      # rebuild REPORT.md and the plots from summary.json")
    add("```")
    add("")
    add("Files: `summary.json` (all numbers), `REPORT.md`, " + ", ".join(f"`{f}`" for f in figs)
        + ", `reference_vectors.json` and `REFERENCE_VECTORS.md` (vectors for the C port).")
    add("")
    text = "\n".join(L)
    for key, func in _NARRATIVE.items():
        text = text.replace(f"@@{key}@@", func(summary))
    return text


def write_report(summary: dict, out_dir: str) -> str:
    """Write ``REPORT.md`` and the figures; returns the path of the report."""
    os.makedirs(out_dir, exist_ok=True)
    figs = make_plots(summary, out_dir)
    text = render(summary, figs)
    path = os.path.join(out_dir, "REPORT.md")
    with open(path, "w") as fh:
        fh.write(text)
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    with open(os.path.join(out_dir, "summary.json")) as fh:
        summary = json.load(fh)
    print("wrote", write_report(summary, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
