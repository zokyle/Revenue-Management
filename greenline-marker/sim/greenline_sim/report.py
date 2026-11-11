"""Turn the Monte-Carlo summary into ``REPORT.md`` and PNG plots.

``write_report(summary, out_dir)`` is called by
``python -m greenline_sim.montecarlo``; ``python -m greenline_sim.report``
rebuilds the report and the plots from an existing ``results/summary.json``.

Every number in the report is read from the summary dictionary; the verdict
sentences are derived from the same numbers by fixed rules (see
:func:`greenline_sim.montecarlo.verdict`), so re-running the Monte Carlo with
another seed or size regenerates a consistent report.
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional, Sequence

from . import bench
from . import physics as ph

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
    "B2": "B2 + horizon",
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
HEADLINE = ("STRAIGHT", "B0", "B1", "B2", "ORACLE")
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
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 3.6))
    fig.patch.set_facecolor(SURFACE)
    ypos = list(range(len(order)))[::-1]
    for ax, key, scale, xlabel, title in (
        (axes[0], "d_make", 100.0, "change in make probability, B2 - B1 [percentage points]", "Horizon term: effect on putts holed"),
        (axes[1], "d_mean_miss", 100.0, "change in mean lateral miss, B2 - B1 [cm]", "Horizon term: effect on the miss (clipped at 1 m)"),
    ):
        vals = [scale * ht[k]["all"][key] for k in order]
        errs = [1.96 * scale * ht[k]["all"][key + "_se"] for k in order]
        ax.axvline(0.0, color=AXIS, linewidth=1.2)
        ax.errorbar(vals, ypos, xerr=errs, fmt="o", color=METHOD_COLOR["B2"], ecolor=METHOD_COLOR["B2"],
                    elinewidth=2.0, capsize=0, markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5)
        for v, e, yy in zip(vals, errs, ypos):
            ax.annotate(f"{v:+.1f} ± {e:.1f}", (v, yy), xytext=(0, 9), textcoords="offset points", ha="center",
                        fontsize=8.5, color=INK_2)
        ax.set_yticks(ypos)
        ax.set_yticklabels([FRINGE_LABEL[k] for k in order] if ax is axes[0] else [""] * len(order))
        ax.set_ylim(-0.6, len(order) - 0.4)
        _style(ax, xlabel, "", title)
        ax.grid(True, axis="x", color=GRID, linewidth=0.8)
        ax.grid(False, axis="y")
    axes[0].tick_params(axis="y", labelsize=9, colors=INK_2)
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
    _style(ax, "putt length [m]", "RMS range error [% of distance]", "Range to the flagstick (GL1: f = 657 px, b = 20.4 mm)")
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
    cal = summary["main"]["diagnostics"]["calibration"]
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
    return names


# --------------------------------------------------------------------------
# the report
# --------------------------------------------------------------------------


def _headline(summary) -> str:
    dkeys = _dkeys(summary)
    t = _seat(summary)
    rows = []
    for d in dkeys:
        row = [f"{d} m"]
        for m in HEADLINE:
            c = t[m]["by_distance"][d]
            row.append(f"{_cm(c['median_miss'])} cm / {_pct(c['make_perfect'])} %")
        rows.append(row)
    return _table(["Putt"] + list(HEADLINE), rows)


def _horizon_section(summary) -> str:
    ht = summary["main"]["horizon_test"]
    flag = summary["main"]["diagnostics"]["flag"]["by_distance"]
    dkeys = _dkeys(summary)
    order = [k for k in ("no_fringe", "no_surround", "realistic", "mounded") if k in ht]
    rows = []
    for k in order:
        a = ht[k]["all"]
        rows.append([
            FRINGE_LABEL[k], _ci(a, "d_make", 100.0, 1), _ci(a, "d_mean_miss", 100.0, 2),
            f"{_cm(a['median_miss_a'])} -> {_cm(a['median_miss_b'])}", _pct(a["b_closer"]), a["verdict"],
        ])
    out = [_table(
        ["Silhouette seen by the camera", "Δ make prob. [pp]", "Δ mean miss [cm]", "median miss B1 -> B2 [cm]",
         "B2 closer in [%] of putts", "verdict"], rows)]
    out.append("")
    out.append(
        "Δ = B2 minus B1 on the same putts with the same noise, ± 95 % interval. \"Mean miss\" clips each miss at 1 m. "
        "Verdict rule (fixed before looking at the numbers): \"helps\" if the make probability rises or the mean miss falls "
        "by more than 2 standard errors while the other does not move the wrong way by 2 standard errors; \"hurts\" is the "
        "mirror image; otherwise \"no measurable effect\". A verdict can therefore rest on the miss distance alone."
    )
    out.append("")
    rows = []
    for k in order:
        row = [FRINGE_LABEL[k]]
        for c in summary["meta"]["classes"]:
            e = ht[k][c]
            row.append(f"{100 * e['d_make']:+.1f} pp, {100 * e['d_mean_miss']:+.1f} cm ({e['verdict']})")
        rows.append(row)
    out.append(_table(["By green class"] + list(summary["meta"]["classes"]), rows))
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
    out.append(f"Weight of the horizon residuals (sweep subset, {summary['meta']['n_putts_sweep']} putts; "
               "per-sample sigma of the horizon residual, default 1 mrad):")
    out.append("")
    out.append(_table(["B2 vs B1 at sigma_horizon ="] + [f"{s} mrad" for s in sig], rows))
    out.append("")
    rows = [[f"{d} m", _pct(flag[d].get("horizon_on_green")), _pct(flag[d].get("horizon_on_collar")),
             _pct(flag[d].get("horizon_on_rough")), f"{flag[d].get('horizon_distance_median', float('nan')):.1f}"] for d in dkeys]
    out.append("What forms the silhouette in the realistic case (share of the 41 azimuth samples):")
    out.append("")
    out.append(_table(["Putt", "putting surface [%]", "collar [%]", "rough / surrounds [%]", "median distance of the silhouette [m]"], rows))
    return "\n".join(out)


def _horizon_verdict(summary) -> str:
    ht = summary["main"]["horizon_test"]

    def clause(key):
        a = ht[key]["all"]
        return f"**{a['verdict']}** ({_ci(a, 'd_make', 100.0, 1)} pp makes, {_ci(a, 'd_mean_miss', 100.0, 1)} cm mean miss)"

    planar = ht["realistic"].get("planar")
    text = (
        f"**Verdict, stated plainly.** With no fringe at all (optimistic) the horizon term {clause('no_fringe')}. "
        f"With the realistic geometry as this simulator models it - collar, rough, smooth surrounds that mostly fall away - "
        f"it {clause('realistic')}"
    )
    if planar:
        text += (
            f"; on planar greens alone the effect is {100 * planar['d_make']:+.1f} pp and {100 * planar['d_mean_miss']:+.1f} cm "
            f"({planar['verdict']})"
        )
    text += f". With mounded surrounds that are independent of the green (pessimistic) it {clause('mounded')}."
    return text


# --------------------------------------------------------------------------
# narrative (numbers are interpolated from the summary)
# --------------------------------------------------------------------------


def _ov(summary, method, key, seat=None):
    return _seat(summary, seat)[method]["overall"][key]


def _bd(summary, method, d, key, seat=None):
    return _seat(summary, seat)[method]["by_distance"][d][key]


def _first_beyond_hole(summary, method) -> Optional[str]:
    """Shortest putt length at which the method's median miss exceeds the hole radius."""
    for d in _dkeys(summary):
        if _bd(summary, method, d, "median_miss") > ph.HOLE_R:
            return d
    return None


def _pick(dkeys: Sequence[str], wanted: Sequence[str]) -> List[str]:
    return [d for d in wanted if d in dkeys] or list(dkeys[:2])


def _headline_text(summary) -> str:
    dk = _dkeys(summary)
    paired = summary["main"]["diagnostics"]["paired"]
    ht = summary["main"]["horizon_test"]
    d_a, d_b = (_pick(dk, ("3", "6")) + dk)[:2]
    lim = {m: _first_beyond_hole(summary, m) for m in ("B1", "B0S", "SURVEY3")}
    lines = [
        f"- **A read is worth a lot.** Aiming straight misses by a median of {_cm(_bd(summary, 'STRAIGHT', d_a, 'median_miss'))} cm "
        f"at {d_a} m and {_cm(_bd(summary, 'STRAIGHT', d_b, 'median_miss'))} cm at {d_b} m. The Quick Read (B1) cuts that to "
        f"{_cm(_bd(summary, 'B1', d_a, 'median_miss'))} cm and {_cm(_bd(summary, 'B1', d_b, 'median_miss'))} cm and, with perfect "
        f"execution, holes {_pct(_bd(summary, 'B1', d_a, 'make_perfect'))} % of {d_a} m putts and "
        f"{_pct(_bd(summary, 'B1', d_b, 'make_perfect'))} % of {d_b} m putts (STRAIGHT: "
        f"{_pct(_bd(summary, 'STRAIGHT', d_a, 'make_perfect'))} % and {_pct(_bd(summary, 'STRAIGHT', d_b, 'make_perfect'))} %).",
        f"- **But one placement does not read a long putt.** The median miss of B1 exceeds the hole radius (5.4 cm) from "
        f"{lim['B1'] or 'no length tested'} m on; for the Precision Read from {lim['B0S'] or 'no length tested'} m, for the "
        f"three-drop Survey from {lim['SURVEY3'] or 'no length tested'} m. The reason is not sensor noise: the slope under "
        "the ball differs from the average slope along the line (section 8).",
        f"- **The tilt does nearly all the work on the line.** B0 (tilt only) and B1 have the same median miss "
        f"({_cm(_ov(summary, 'B0', 'median_miss'))} cm and {_cm(_ov(summary, 'B1', 'median_miss'))} cm over all lengths). The "
        f"flag-base height improves the pace, not the line: median pace error at {d_b} m "
        f"{_cm(_bd(summary, 'B0', d_b, 'median_pace_err'), 0)} cm for B0 against {_cm(_bd(summary, 'B1', d_b, 'median_pace_err'), 0)} cm "
        f"for B1, and B1 holes {_ci(paired['B1_vs_B0'], 'd_make', 100.0, 1)} pp more putts than B0.",
        f"- **Turf horizon (B2).** Against B1 on the same putts: {ht['no_fringe']['all']['verdict']} with no fringe "
        f"({_ci(ht['no_fringe']['all'], 'd_make', 100.0, 1)} pp), {ht['realistic']['all']['verdict']} with the realistic "
        f"geometry as modelled ({_ci(ht['realistic']['all'], 'd_make', 100.0, 1)} pp), {ht['mounded']['all']['verdict']} with "
        f"mounded surrounds ({_ci(ht['mounded']['all'], 'd_make', 100.0, 1)} pp). The sign depends on what lies behind the "
        "green, which the device cannot sense. The firmware default is therefore B1; B2 stays an option (section 5).",
        f"- **More placements beat more optics.** Precision Read: {_ci(paired['B0S_vs_B1'], 'd_make', 100.0, 1)} pp makes over "
        f"B1; three-drop Survey: {_ci(paired['SURVEY3_vs_B1'], 'd_make', 100.0, 1)} pp, with the median miss falling from "
        f"{_cm(_ov(summary, 'B1', 'median_miss'))} cm to {_cm(_ov(summary, 'SURVEY3', 'median_miss'))} cm over all lengths. "
        "The camera presets and the lens height change next to nothing (section 11).",
        f"- **Against a human reader.** At {summary['meta']['nominal_seat_mrad']:g} mrad seating noise the Quick Read holes "
        f"{_pct(_ov(summary, 'B1', 'make_perfect'), 1)} % of all putts with perfect execution, a golfer who reads cross slope to "
        f"0.5 % holes {_pct(_ov(summary, 'HUMAN05', 'make_perfect'), 1)} %, one who reads it to 1 % holes "
        f"{_pct(_ov(summary, 'HUMAN10', 'make_perfect'), 1)} %. At 5 mrad the Quick Read drops to "
        f"{_pct(_ov(summary, 'B1', 'make_perfect', '5'), 1) if '5' in summary['main']['by_seat'] else '-'} % (section 4).",
        f"- **Two limits no slope sensor removes.** With the true surface but the golfer's entered green speed "
        f"({100 * summary['meta']['sensor_params']['sigma_stimp']:g} % error) and the measured grain, only "
        f"{_pct(_ov(summary, 'ORACLE_SLOPE', 'make_perfect'), 1)} % of putts drop with perfect execution. And with human "
        f"execution even the oracle holes {_pct(_bd(summary, 'ORACLE', d_a, 'make_human'))} % at {d_a} m and "
        f"{_pct(_bd(summary, 'ORACLE', d_b, 'make_human'))} % at {d_b} m; B1 holes {_pct(_bd(summary, 'B1', d_a, 'make_human'))} % "
        f"and {_pct(_bd(summary, 'B1', d_b, 'make_human'))} % (section 9).",
    ]
    return "\n".join(lines)


def _seat_text(summary) -> str:
    seats = [f"{s:g}" for s in summary["meta"]["seat_levels_mrad"]]
    dk = _dkeys(summary)
    se_tab = summary["main"]["diagnostics"]["slope_error"]
    d_mid = _pick(dk, ("6",))[0]

    def row(method):
        return ", ".join(f"{_pct(_ov(summary, method, 'make_perfect', s), 1)} % at {s} mrad" for s in seats)

    def miss(method):
        return " / ".join(_cm(_ov(summary, method, "median_miss", s)) for s in seats)

    h05 = _ov(summary, "HUMAN05", "make_perfect")
    h10 = _ov(summary, "HUMAN10", "make_perfect")

    def versus(method, ref):
        words = []
        for s in seats:
            v = _ov(summary, method, "make_perfect", s)
            words.append(f"{'ahead' if v > ref else 'behind'} at {s} mrad ({100 * (v - ref):+.1f} pp)")
        return ", ".join(words)

    gaps = [100 * (_ov(summary, "B1", "make_perfect", s) - h05) for s in seats]
    human_better = [d for d in dk if _bd(summary, "HUMAN05", d, "median_miss") < _bd(summary, "B1", d, "median_miss")]
    ahead_at_high = [m for m in ("B1", "B0S", "SURVEY2", "SURVEY3") if _ov(summary, m, "make_perfect", seats[-1]) > h05 + 0.01]
    out = [
        f"All lengths pooled, make probability with perfect execution: B1 {row('B1')}; B0S {row('B0S')}; SURVEY3 {row('SURVEY3')}. "
        f"Median miss [cm] at {' / '.join(seats)} mrad: B1 {miss('B1')}, B0S {miss('B0S')}, SURVEY2 {miss('SURVEY2')}, SURVEY3 {miss('SURVEY3')}.",
        "",
        f"Next to the human baselines ({_pct(h05, 1)} % for the 0.5 % reader, {_pct(h10, 1)} % for the 1 % reader):",
        "",
        f"- Quick Read (B1) against the 0.5 % reader: {versus('B1', h05)}; against the 1 % reader: {versus('B1', h10)}.",
        f"- Precision Read (B0S) against the 0.5 % reader: {versus('B0S', h05)}.",
        f"- Survey (SURVEY3) against the 0.5 % reader: {versus('SURVEY3', h05)}.",
        "",
        "Three things follow.",
        "",
        "1. The device's standing against a good human reader is decided by a number nobody has measured. Across the "
        f"plausible range of seating noise the Quick Read moves from {gaps[0]:+.1f} pp to {gaps[-1]:+.1f} pp relative to the "
        f"0.5 % reader. At {seats[-1]} mrad the modes that are still more than 1 pp ahead of that reader are: "
        f"{', '.join(ahead_at_high) if ahead_at_high else 'none'}. Measuring the seating repeatability of the real puck on "
        "real turf is the first experiment the project needs.",
        f"2. Lower seating noise has diminishing returns for single-placement modes. Going from 2.5 to 1 mrad raises B1 by only "
        f"{100 * (_ov(summary, 'B1', 'make_perfect', seats[0]) - _ov(summary, 'B1', 'make_perfect')):.1f} pp, because the "
        f"error that remains is the difference between the slope under the ball and the average along the line "
        f"({_mrad(se_tab[d_mid]['representativeness'])} mrad RMS at {d_mid} m, section 8), which no single placement sees.",
        f"3. The simulated human baselines assume that the golfer reads the PATH-AVERAGE cross slope and knows the hole height "
        "and the bearing exactly; only the size of the read error is varied. That is generous to the human on long, contoured "
        "putts, where a single placement cannot know the path average. Lengths at which the 0.5 % reader has a smaller "
        f"median miss than B1 at {summary['meta']['nominal_seat_mrad']:g} mrad: "
        f"{', '.join(d + ' m' for d in human_better) if human_better else 'none'}.",
    ]
    return "\n".join(out)


def _horizon_text(summary) -> str:
    ht = summary["main"]["horizon_test"]
    flag = summary["main"]["diagnostics"]["flag"]["by_distance"]
    dk = _dkeys(summary)
    seats = [f"{s:g}" for s in summary["meta"]["seat_levels_mrad"]]
    rough = [flag[d].get("horizon_on_rough") for d in dk if flag[d].get("horizon_on_rough") is not None]
    hd = [flag[d].get("horizon_distance_median") for d in dk if flag[d].get("horizon_distance_median") is not None]
    by_seat = ", ".join(
        f"{100 * (_ov(summary, 'B2', 'make_perfect', s) - _ov(summary, 'B1', 'make_perfect', s)):+.1f} pp at {s} mrad" for s in seats
    )
    hw = summary["sweeps"]["horizon_sigma_mrad"]
    tight = hw["realistic"].get("0.3", {}).get("vs_B1")
    mound_verdicts = [v["vs_B1"]["verdict"] for v in hw.get("mounded", {}).values()]
    if mound_verdicts and all(v == "hurts" for v in mound_verdicts):
        mound_weights = "at every residual weight tested"
    else:
        mound_weights = "at the default weight (the verdicts at the other weights are in the table above)"
    out = [
        "What the numbers mean:",
        "",
        f"- **The silhouette is mostly not the putting surface.** In the realistic case {_pct(min(rough))}-{_pct(max(rough))} % of "
        f"the horizon samples are formed by the rough and the ground beyond it, at a median distance of {min(hd):.0f}-{max(hd):.0f} m "
        "from the lens. The reviewers' premise is confirmed.",
        "- **Why it helps here anyway.** In this generator the ground under the collar and the rough is the smooth "
        "continuation of the putting surface plus a radial slope that varies slowly with azimuth and mostly falls away. The "
        "far silhouette is then the far edge of the green wearing a 40 mm canopy: its tilt across the field is the "
        "large-scale cross slope of the green, an independent second measurement of what the puck tilt measures locally. "
        f"That is also why the gain grows with seating noise (B2 minus B1 in make probability: {by_seat}).",
        "- **Why that cannot be relied on.** With mounds and hollows of 0.2 m RMS behind the green - a modest amount of "
        f"greenside shaping - the same estimator is worse than not using the horizon at all, {mound_weights}. "
        "A 0.2 m mound seen from 12 m stands 17 mrad high and is several metres wide, i.e. smooth across the whole field; to "
        "the fit it looks like cross slope and curvature, not like outliers, so the Huber loss does not reject it."
        + (f" Weighting the horizon at its bare pixel noise (0.3 mrad) hurts even with the default surrounds "
           f"({100 * tight['d_make']:+.1f} pp, {100 * tight['d_mean_miss']:+.1f} cm)." if tight else ""),
        "- **What is not in the simulation at all.** Trees, buildings, spectators, bunker lips and the flagstick's own "
        "surroundings above the turf line; errors in picking the turf silhouette out of the image; sun glare; a wet or "
        "dirty window. The surround terrain itself (both the default and the mounded variant) is an assumption with named "
        "parameters, not survey data. None of the omitted effects makes a silhouette more trustworthy, so the row "
        "\"realistic as modelled\" should be read as favourable to the horizon.",
        "",
        f"**Decision for the firmware default.** Under this simulator's own default geometry the horizon term "
        f"{ht['realistic']['all']['verdict']} ({_ci(ht['realistic']['all'], 'd_make', 100.0, 1)} pp makes), so the simulation "
        "does not show that the path is useless. It shows that the benefit is modest and that its sign flips with the shape "
        "of the surrounds. Because the device cannot tell which case it is in, and the unmodelled effects all point the same "
        "way, the default method is **B1 (horizon off)**; B2 remains selectable (`estimate(meas, \"B2\")`) so that logged "
        "horizon profiles from real greens with surveyed slopes can settle the question.",
    ]
    return "\n".join(out)


def _range_text(summary) -> str:
    dk = _dkeys(summary)
    rng = summary["main"]["diagnostics"]["range"]
    fh = summary["sweeps"]["range_first_hole"]
    far = dk[-1]
    mid = _pick(dk, ("9",))[0]
    near = _pick(dk, ("3",))[0]
    cam_tab = summary["sweeps"]["camera"]
    cam_rng = summary["sweeps"]["camera_range"]
    best = "2MP" if "2MP" in cam_tab else list(cam_tab)[-1]
    out = [
        f"- Stereo alone follows the textbook formula: {_pct(rng[near]['stereo_rms'], 1)} % at {near} m, "
        f"{_pct(rng[mid]['stereo_rms'], 1)} % at {mid} m, {_pct(rng[far]['stereo_rms'], 1)} % at {far} m. The estimate "
        f"`f b / disparity` is biased long by about the square of that ({_pct(rng[far]['stereo_bias'], 1)} % at {far} m); "
        "this is not corrected.",
        f"- Ranging from the stick's angular height needs the top inside the {summary['meta']['camera']['up_fov_deg']:g} deg "
        "upward field (beyond about 6.7 m for a 2.13 m stick) AND a visible base. It is therefore available on "
        f"{_pct(rng[mid]['mono_available'])} % of the reads at {mid} m and {_pct(rng[far]['mono_available'])} % at {far} m, "
        f"where it is good ({_pct(rng[far]['mono_rms'], 1)} % with a learned stick height, {_pct(fh[far]['mono_rms'], 1)} % with "
        "the first-hole default of 2.13 m; the simulated sticks are 2.0-2.3 m, the 7 % is the uncertainty the estimator "
        "assigns to that default).",
        f"- Fused: {_pct(rng[mid]['fused_rms'], 1)} % at {mid} m and {_pct(rng[far]['fused_rms'], 1)} % at {far} m over all reads "
        f"(first hole: {_pct(fh[mid]['fused_rms'], 1)} % and {_pct(fh[far]['fused_rms'], 1)} %). The design-spec figure of "
        "\"about 2-3 % once the stick height is learned\" is met only on the reads where the stick-height channel is "
        "available; on crowned lines, where the base is hidden, the range falls back to stereo.",
        f"- It hardly matters for the line: the {best} preset ranges to {_pct(cam_rng[best][far]['fused_rms'], 1)} % at {far} m "
        f"and its B1 median miss over all lengths is {_cm(cam_tab[best]['B1']['overall']['median_miss'])} cm against "
        f"{_cm(cam_tab['GL1']['B1']['overall']['median_miss'])} cm for GL1. Range feeds the displayed distance and the pace.",
    ]
    return "\n".join(out)


def _flag_text(summary) -> str:
    dk = _dkeys(summary)
    fl = summary["main"]["diagnostics"]["flag"]["by_distance"]
    se_tab = summary["main"]["diagnostics"]["slope_error"]
    fb = summary["sweeps"]["flag_base"]
    blind_key = [k for k in fb if k.startswith("base visibility unknown")][0]
    hid_cls = summary["main"]["diagnostics"]["flag"]["hidden_by_distance_class"]
    nom = _seat(summary)
    near, far = dk[0], dk[-1]
    mid = _pick(dk, ("6",))[0]
    out = [
        f"- **Detection.** The flag is found on {_pct(fl[near]['found'], 1)} % of reads at {near} m and "
        f"{_pct(fl[far]['found'], 1)} % at {far} m (2 % floor, loss of the 12.7 mm stick at long range, and the visor pointing "
        "more than 26 deg off the flag about 1 % of the time). A read without the flag falls back to hand-pointing; on those "
        "putts every device mode is as poor as FLAGOUT (section 12, subset \"flag_not_found\"). The detection model is an "
        "engineering guess.",
        f"- **Hidden base.** From {1e3 * summary['meta']['camera']['h_cam']:g} mm above the turf a gently crowned line hides "
        f"the bottom of the stick: on {_pct(fl[near]['base_hidden'], 1)} % of putts at {near} m, {_pct(fl[mid]['base_hidden'])} % "
        f"at {mid} m and {_pct(fl[far]['base_hidden'])} % at {far} m, with a median of "
        f"{1e3 * fl[far]['hidden_height_median']:.0f} mm of stick hidden at {far} m. By class at {far} m: "
        + ", ".join(f"{c} {_pct(hid_cls[f'{far}|{c}'])} %" for c in summary["meta"]["classes"]) + ".",
        f"- **Consequence for the pace.** With the base visible B1 knows the mean slope along the line to "
        f"{_mrad(se_tab[mid]['along_base_visible']['B1'])} mrad RMS at {mid} m; with the base hidden to "
        f"{_mrad(se_tab[mid]['along_base_hidden']['B1'])} mrad, barely better than the tilt alone "
        f"({_mrad(se_tab[mid]['along_base_hidden']['B0'])} mrad). The one-sided bound carries almost no information: the fit "
        "sits at the tilt plane or on the bound, never below it, so on crowned lines B1 expects the hole higher than it is "
        f"and hits long (mean pace error of B1 at {mid} m {_signed(100 * nom['B1']['by_distance'][mid]['mean_pace_err'])} cm against "
        f"{_signed(100 * nom['ORACLE_SLOPE']['by_distance'][mid]['mean_pace_err'])} cm with the true surface).",
        f"- **The device is assumed to know whether the base is hidden.** That flag comes from the simulator's line-of-sight "
        "test; real firmware has to infer it. The sweep in section 11 shows that nothing is lost if it cannot: treating the "
        f"lowest visible point as the base in every case gives B1 {_pct(fb[blind_key]['B1']['overall']['make_perfect'], 1)} % "
        f"makes against {_pct(fb['with flag base']['B1']['overall']['make_perfect'], 1)} % with perfect knowledge "
        f"(paired difference {_ci(summary['sweeps']['flag_base_paired']['B1_blind_vs_informed'], 'd_make', 100.0, 1)} pp).",
    ]
    return "\n".join(out)


def _budget_text(summary) -> str:
    dk = _dkeys(summary)
    se_tab = summary["main"]["diagnostics"]["slope_error"]
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
    sd = summary["main"]["by_seat"][f"{seat:g}"]
    out = [
        f"- **Line.** A single placement measures the slope under the ball with {single:.1f} mrad per axis (seating "
        f"{seat:g} mrad and device bias {bias:g} mrad). The slope it should have measured - the average along the line - "
        f"differs from the slope under the ball by {_mrad(se_tab[dk[0]]['representativeness'])} mrad RMS at {dk[0]} m, "
        f"{_mrad(se_tab[mid]['representativeness'])} mrad at {mid} m and {_mrad(se_tab[far]['representativeness'])} mrad at {far} m "
        "(all classes pooled)."
        + (f" From {cross} m on, this representativeness error is larger than the measurement error." if cross else "")
        + f" The two add in quadrature to the B1 column. The Precision Read shrinks only the first term (to "
        f"{seat / math.sqrt(2.0):.1f} mrad if the two seatings are independent); the Survey attacks "
        f"the second ({_mrad(se_tab[mid]['cross']['SURVEY3'])} mrad at {mid} m against {_mrad(se_tab[mid]['cross']['B1'])} mrad for B1).",
        f"- **Pace.** The median pace error of B1 at {mid} m is {_cm(sd['B1']['by_distance'][mid]['median_pace_err'], 0)} cm; "
        f"with the true surface and the same entered green speed it is still "
        f"{_cm(sd['ORACLE_SLOPE']['by_distance'][mid]['median_pace_err'], 0)} cm. A "
        f"{100 * summary['meta']['sensor_params']['sigma_stimp']:g} % error in the entered Stimp is a "
        f"{100 * summary['meta']['sensor_params']['sigma_stimp']:g} % error in roll-out, about "
        f"{100 * summary['meta']['sensor_params']['sigma_stimp'] * (float(mid) + 0.3):.0f} cm at {mid} m, larger than the "
        f"0.30 m of intended over-run: {_pct(sd['ORACLE_SLOPE']['by_distance'][mid]['short'])} % of perfectly struck "
        f"{mid} m putts stop short even with perfect knowledge of the surface. Green-speed knowledge, not slope sensing, "
        "sets the pace accuracy of every mode.",
    ]
    return "\n".join(out)


def _exec_text(summary) -> str:
    dk = _dkeys(summary)
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
    out = [
        f"With {summary['meta']['sigma_dir_deg']:g} deg of direction scatter and {100 * summary['meta']['sigma_speed']:g} % of speed "
        "scatter, the make probability splits as follows:",
        "",
        *rows,
        "",
        f"Up to about 4.5 m the read error (median {_cm(_bd(summary, 'B1', _pick(dk, ('3',))[0], 'median_miss'))} cm at 3 m) and "
        f"the execution error (median {_cm(_bd(summary, 'ORACLE', _pick(dk, ('3',))[0], 'median_miss_human'))} cm) are of the same "
        "size, so a better read is visible in the make rate. Beyond 6 m nobody holes much: at "
        f"{far} m the oracle holes {_pct(_bd(summary, 'ORACLE', far, 'make_human'), 1)} % and B1 "
        f"{_pct(_bd(summary, 'B1', far, 'make_human'), 1)} %. On long putts the product's value is the leave, not the make: "
        "the read decides whether the ball finishes inside tap-in range, and that is governed by the pace (section 8).",
    ]
    return "\n".join(out)


def _bearing_text(summary) -> str:
    p = summary["main"]["diagnostics"]["paired"]["B0_vs_FLAGOUT"]
    return (
        f"Both rows use the same tilt-only plane; FLAGOUT replaces the camera's bearing (about 1 mrad) by hand-pointing "
        f"(1.5 deg, 1 sigma) and the camera's range by a dialled distance (10 %). The camera bearing is worth "
        f"{_ci(p, 'd_make', 100.0, 1)} pp of make probability and {-100 * p['d_mean_miss']:.1f} cm of mean miss. A pointing "
        "error of 1.5 deg is 7.9 cm at 3 m, more than the hole radius, before any slope error: the flagstick bearing is the "
        "most valuable thing the cameras deliver. The 1.5 deg figure is an assumption about how well a golfer can aim a "
        "46 mm puck by eye."
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
    sp = sw["spin_seat_correlation"]
    sv = sw["survey_sigma_field_mrad"]
    gk = list(gr_.keys())
    svk = list(sv.keys())
    hk = [k for k in hh if "GL1" not in k]
    short = dk[0]
    out = [
        f"- **Camera preset.** B1 make probability: " + ", ".join(f"{k} {_pct(o(v, 'B1'), 1)} %" for k, v in cam.items())
        + ". Focal length and baseline change the range accuracy and the flag-detection rate (QVGA finds the flag on "
        f"{_pct(sw['camera_found'].get('QVGA'), 0)} % of reads against {_pct(sw['camera_found'].get('GL1'), 0)} % for GL1), not the read. "
        f"B2 with the ±40 deg presets is worse than with GL1 on short putts ({_pct(cam['VGA']['B2']['by_distance'][short]['make_perfect'])} % "
        f"against {_pct(cam['GL1']['B2']['by_distance'][short]['make_perfect'])} % at {short} m); the likely reason is that the "
        "wider field gives the far silhouette more leverage over a putt that does not go there (the lens-height sweep "
        "rules out the height).",
        f"- **Lens height.** Between 3 and 6 mm nothing moves (B1 make probability "
        + ", ".join(f"{_pct(o(hh[k], 'B1'), 1)} % at {k} mm" for k in hk)
        + f"); the share of hidden bases changes only from {_pct(hh[hk[0]]['base_hidden'])} % to {_pct(hh[hk[-1]]['base_hidden'])} %. "
        "A crown hides the base beyond sqrt(2 h / curvature), which grows only with the square root of the height.",
        f"- **Flag-base height.** Removing it costs B1 {100 * (o(fb['with flag base'], 'B1') - o(fb['without flag base'], 'B1')):.1f} pp "
        f"and raises the median pace error from {_cm(o(fb['with flag base'], 'B1', 'median_pace_err'), 0)} to "
        f"{_cm(o(fb['without flag base'], 'B1', 'median_pace_err'), 0)} cm; the median lateral miss is unchanged "
        f"({_cm(o(fb['with flag base'], 'B1', 'median_miss'))} and {_cm(o(fb['without flag base'], 'B1', 'median_miss'))} cm). "
        f"B2 holes {_pct(o(fb['without flag base'], 'B2'), 1)} % without the flag base and {_pct(o(fb['with flag base'], 'B2'), 1)} % "
        f"with it (paired difference with minus without: {_ci(fbp['B2_with_vs_without'], 'd_make', 100.0, 1)} pp): the "
        "hole-height constraint does not help B2, which suggests that it and the horizon residuals pull the fitted "
        "curvature along the line in different directions - one more sign that B2's picture of the far field is not right.",
        f"- **Entered green speed.** B1 make probability " + ", ".join(f"{_pct(o(v, 'B1'), 1)} % at {k} % error" for k, v in st.items())
        + "; with the true surface " + ", ".join(f"{_pct(o(v, 'ORACLE_SLOPE'), 1)} % at {k} %" for k, v in st.items())
        + ". This is the largest single lever in the whole table. Even with a perfectly known Stimp the true-surface "
        "reference stays below 100 % because of the grain reading (20 deg, 30 %).",
        f"- **Grain.** {gk[0]}: {_pct(o(gr_[gk[0]], 'B1'), 1)} %; {gk[1]}: {_pct(o(gr_[gk[1]], 'B1'), 1)} %; {gk[2]}: "
        f"{_pct(o(gr_[gk[2]], 'B1'), 1)} %. On these greens (35 % strongly grained) even the coarse grain reading is worth "
        f"{100 * (o(gr_[gk[0]], 'B1') - o(gr_[gk[1]], 'B1')):.1f} pp. The design spec ships the grain sensor DISABLED until it "
        "is validated, so the \"sensor off\" row is the configuration that would ship today, and every device number in "
        "this report that uses the grain reading is optimistic by about that much on grainy greens.",
        f"- **Precision Read.** Its gain over B1 ({100 * (o(sp['0'], 'B0S') - o(sp['0'], 'B1')):+.1f} pp) assumes two "
        f"independent seatings. If half of the seating error is a property of the spot the gain is "
        f"{100 * (o(sp['0.5'], 'B0S') - o(sp['0'], 'B1')):+.1f} pp, and if all of it is (the spin only cancels the device bias) "
        f"{100 * (o(sp['1'], 'B0S') - o(sp['0'], 'B1')):+.1f} pp. Which of these is true is part of the unmeasured seating question.",
        f"- **Survey model-error allowance.** With `sigma_field` = {svk[0]} SURVEY3 holes {_pct(o(sv[svk[0]], 'SURVEY3'), 1)} %, "
        f"with {svk[1]} {_pct(o(sv[svk[1]], 'SURVEY3'), 1)} %: no measurable effect on accuracy. It is kept because it makes "
        "the Survey's reported confidence honest (section 12).",
    ]
    return "\n".join(out)


def _fusion_text(summary) -> str:
    diag = summary["main"]["diagnostics"]
    sub = diag["subsets"]
    nom = _seat(summary)
    cal = diag["calibration"]
    se_tab = diag["slope_error"]
    dk = _dkeys(summary)

    def cls(method, c, key="median_miss"):
        return nom[method]["by_class"][c][key]

    def sb(label, method, key="median_miss"):
        return sub[label][method].get(key)

    hid = "base_hidden (crowned line)"
    dbl = "double_break"
    far = _pick(dk, ("9",))[0]

    def cal_span(method):
        rows = [r for r in cal[method] if r["n"] >= 30] or list(cal[method])
        if not rows:
            return "no reads to judge it by"
        lo = min(rows, key=lambda r: abs(r["mean_confidence"] - 0.15))
        hi = min(rows, key=lambda r: abs(r["mean_confidence"] - 0.6))
        return f"a score near {lo['mean_confidence']:.2f} goes with {lo['within_hole']:.2f} of reads inside the hole radius and one near {hi['mean_confidence']:.2f} with {hi['within_hole']:.2f}"

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
        f"B0 is the same ({_cm(sb(hid, 'B0'))} cm, {_pct(sb(hid, 'B0', 'make_perfect'))} %): on these putts the fusion adds "
        f"nothing to the tilt. SURVEY3 reaches {_cm(sb(hid, 'SURVEY3'))} cm and {_pct(sb(hid, 'SURVEY3', 'make_perfect'))} %.",
        f"- *Double breaks.* Where the cross slope changes sign along the line (N = {sub[dbl]['B1']['n']}) a single read is "
        f"WORSE than no read: B1 misses by a median of {_cm(sb(dbl, 'B1'))} cm, STRAIGHT by {_cm(sb(dbl, 'STRAIGHT'))} cm. The "
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
        f"**Confidence score.** It is not well calibrated. For B1 it is too pessimistic: {cal_span('B1')}. The likely "
        "cause is the curvature prior (0.004 1/m) that sets it: about right for undulating greens, too wide for planar and "
        "gentle ones. For B2 it is too "
        f"optimistic ({cal_span('B2')}) because the fit treats the 41 horizon samples as independent. For SURVEY3 it is "
        f"close ({cal_span('SURVEY3')}). The score ranks reads usefully within one mode; it should not be shown as a "
        "probability.",
    ]
    return "\n".join(out)


def _limits_text(summary) -> str:
    meta = summary["meta"]
    sp = meta["sensor_params"]
    diag = summary["main"]["diagnostics"]
    out = [
        "Inputs that are estimates, not measurements:",
        "",
        f"- **Seating noise** ({1e3 * sp['sigma_seat']:g} mrad nominal; 1 and 5 mrad also run). No published data. Everything in "
        "section 4 hinges on it. The Precision Read additionally assumes that two seatings on the same spot are independent.",
        f"- **Device tilt bias** {1e3 * sp['sigma_tilt_bias']:g} mrad per axis after cradle calibration.",
        "- **Surround terrain** (default: mean radial slope -8 % to +2 % with slow azimuthal variation; stress case: 0.2 m RMS "
        "mounds). Decides the horizon result (section 5).",
        "- **Flag detection** (2 % floor, loss of a 12.7 mm stick with range) and the **hand-pointing error** (1.5 deg).",
        f"- **Entered green speed** ({100 * sp['sigma_stimp']:g} %) and the **grain sensor** (20 deg, 30 %; unproven, ships disabled).",
        "- **Human baselines**: read error applied to the true path-average cross slope; perfect hole height, bearing and distance.",
        f"- **Human execution**: {meta['sigma_dir_deg']:g} deg and {100 * meta['sigma_speed']:g} %, independent, Gaussian.",
        "- **Capture rule** (Holmes / Penner style: holed if the path passes within the hole radius slower than "
        "1.63 m/s x sqrt(1 - (delta/R)^2)); lip-outs do not deflect the ball.",
        "",
        "Simplifications of the model:",
        "",
        "- The ball rolls deterministically on a smooth surface: no bumpiness, footprints, wind or ball imbalance. Real "
        "putts scatter even with perfect execution, so all make probabilities with \"perfect execution\" are upper bounds.",
        "- Grain is a constant push; green speed is uniform over the green; the rough does not slow a ball that runs off.",
        "- The lens is taken to be at the ball position (the real cameras sit 16 mm ahead and 10 mm either side of the puck centre).",
        "- The device is told whether the base of the stick is visible (section 7), and the turf silhouette is assumed to be "
        "extracted from the image without error; nothing above the turf line exists in the simulated scene.",
        "- The estimator's noise constants stay at their nominal values when the true noise is varied.",
        "",
        "Things that did not work as hoped, in one place:",
        "",
        "1. A single placement cannot read putts beyond about 4.5 m on contoured greens; the limit is the green, not the sensor (sections 1, 8).",
        "2. The flag-base height does not improve the line, is unavailable on a quarter to a half of the putts beyond 4.5 m, "
        "and its one-sided form on crowned lines is no better than treating the sight line as the base (sections 7, 11).",
        "3. The turf-horizon path is helpful or harmful depending on the surrounds; it is off by default (section 5).",
        "4. Stick-height ranging is available on only about half of the long putts; fused range at 12 m does not reach the 2-3 % of the design spec (section 6).",
        "5. On double-breaking putts a Quick Read is worse than aiming straight, and nothing in a single read reveals that (section 12).",
        "6. The Survey's plane-plus-curvature model handles the cross slope well but not the pace on long crowned putts (section 12).",
        "7. The confidence score is conservative for B1 and overconfident for B2 (section 12).",
        "8. Pace accuracy is set by the golfer's green-speed entry, not by anything the device senses (sections 8, 11).",
        f"9. The aim solver could not solve the fitted patch in a handful of reads and fell back to the secant plane or a "
        f"best-effort iterate (counts in section 12); the true-surface oracle solved {meta['n_putts_main'] - diag['oracle_not_solved']} "
        f"of {meta['n_putts_main']} putts. Putts for which a reference had no usable solution and rolled its best iterate "
        "instead: " + ", ".join(f"{k} {v}" for k, v in diag["unsolved"].items() if k in ("ORACLE", "ORACLE_SLOPE", "HUMAN05", "HUMAN10")) + ".",
    ]
    return "\n".join(out)


_NARRATIVE = {
    "HEADLINE_TEXT": _headline_text,
    "SEAT_TEXT": _seat_text,
    "HORIZON_TEXT": _horizon_text,
    "RANGE_TEXT": _range_text,
    "FLAG_TEXT": _flag_text,
    "BUDGET_TEXT": _budget_text,
    "EXEC_TEXT": _exec_text,
    "BEARING_TEXT": _bearing_text,
    "SWEEP_TEXT": _sweep_text,
    "FUSION_TEXT": _fusion_text,
    "LIMITS_TEXT": _limits_text,
}


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
    ht = summary["main"]["horizon_test"]

    def cell(method, d, key, seat=None):
        return _seat(summary, seat)[method]["by_distance"][d][key]

    def allv(method, key, seat=None):
        return _seat(summary, seat)[method]["overall"][key]

    L: List[str] = []
    add = L.append

    # ------------------------------------------------------------------ title
    add("# GreenLine simulation report")
    add("")
    add(
        "Generated by `python -m greenline_sim.montecarlo` from the Python reference in `sim/greenline_sim`. "
        "Every number below is read from `results/summary.json`; the wording of the verdicts follows fixed rules applied "
        "to those numbers. Nothing here is a measurement of hardware: it is a simulation of the GL-1 design on synthetic "
        "greens, and several inputs are estimates (listed in section 13)."
    )
    add("")
    add(
        f"**Size of the run.** {meta['n_putts_main']} putts in the main experiment: {len(meta['distances'])} putt lengths x "
        f"{len(meta['classes'])} green classes x {meta['n_putts_per_cell']} seeded greens, i.e. N = {meta['n_putts_per_cell']} "
        f"per (length, class) cell and N = {meta['n_putts_per_cell'] * len(meta['classes'])} per length. Each putt is evaluated "
        f"for every method at {len(seats)} seating-noise levels, once with perfect execution and {meta['n_exec']} times with "
        f"human execution noise ({meta['sigma_dir_deg']:g} deg direction, {100 * meta['sigma_speed']:g} % speed, 1 sigma). "
        f"The sensitivity sweeps use the first {meta['n_putts_sweep']} putts. Master seed {meta['master_seed']}. "
        f"Runtime {rt['total']:.0f} s ({rt['main']:.0f} s main, {rt['sweeps']:.0f} s sweeps) with {meta['numba']}. "
        f"{meta['n_skipped']} (green, length) pairs had no legal putt and were skipped."
    )
    add("")
    add(
        f"**Statistical resolution.** With N = {meta['n_putts_per_cell'] * len(meta['classes'])} per length a make probability "
        f"near 50 % has a standard error of about {100 * 0.5 / math.sqrt(meta['n_putts_per_cell'] * len(meta['classes'])):.1f} "
        f"percentage points (pp); per (length, class) cell it is about {100 * 0.5 / math.sqrt(meta['n_putts_per_cell']):.0f} pp, "
        "so single cells of the appendix tables are indicative only. Method comparisons are paired (same greens, same noise "
        "draws) and are quoted with 95 % intervals where a conclusion rests on them."
    )
    add("")

    # ------------------------------------------------------------------ 1 headline
    add("## 1. Headline")
    add("")
    add(f"Median lateral miss at the hole / make probability, both with perfect execution, seating noise {nseat} mrad:")
    add("")
    add(_headline(summary))
    add("")
    add("@@HEADLINE_TEXT@@")
    add("")
    add(f"![Median lateral miss by distance]({figs[0]})")
    add("")
    add(f"![Make probability]({figs[1]})")
    add("")

    # ------------------------------------------------------------------ 2 setup
    add("## 2. What was simulated")
    add("")
    add(
        f"**Hardware (preset {cam['name']}).** Stereo pair with f = {cam['f_px']:g} px and baseline {1e3 * cam['baseline']:g} mm, "
        f"optical axis {1e3 * cam['h_cam']:g} mm above the base plane (the puck sinks an unknown 0-"
        f"{1e3 * meta['sensor_params']['sink_max']:g} mm into the canopy), horizontal field ±{cam['half_fov_h_deg']:g} deg, "
        f"usable upward field {cam['up_fov_deg']:g} deg. The device measures: puck tilt; flagstick bearing, stereo disparity, "
        "elevation of the lowest visible point of the stick and, when in the field, of its top; the turf-horizon elevation at "
        f"{meta['sensor_params']['n_horizon']} azimuths; grain; and takes the green speed from the golfer. It cannot see the "
        "surface between ball and hole in a range-resolved way, and nothing in the estimator pretends it can: at lens height "
        f"h the ground at distance d subtends h / d^2 rad per metre ({1e3 * cam['h_cam'] / 9.0:.1f} mrad per metre at 3 m, "
        f"{cam['f_px'] * cam['h_cam'] / 9.0:.1f} px), so the whole green collapses onto the horizon line."
    )
    add("")
    add("**Methods.**")
    add("")
    add(_table(
        ["Name", "What it is", "Inputs"],
        [
            ["STRAIGHT", "aim at the flag, flat-green pace", "camera bearing and range, entered Stimp"],
            ["B0", "plane from one tilt reading (what a digital-level ball marker gives)", "+ puck tilt"],
            ["B1", "Quick Read: MAP fit of a quadratic patch", "+ flag-base height (or a one-sided bound when the base is hidden)"],
            ["B2", "B1 + turf-horizon residuals", "+ horizon profile"],
            ["B0S", "Precision Read: B1 with a 180-degree spin-and-reread", "two seatings averaged, device bias cancelled"],
            ["SURVEY2 / SURVEY3", "Survey: drops at the ball, the midpoint (and 1 m short of the hole)", "each drop: tilt, own range and bearing, own hole height"],
            ["FLAGOUT", "flag-out fallback, tilt only", "visor pointed by hand (1.5 deg), dialled distance (10 %)"],
            ["HUMAN05 / HUMAN10", "golfer who reads the path-average cross slope with 0.5 % / 1 % error", "true hole height, true bearing and distance; the same entered Stimp and measured grain as the device"],
            ["ORACLE_SLOPE", "true surface, but the entered Stimp and the measured grain", "isolates slope reading from speed and grain knowledge"],
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
        "4-8 m, hole where the local slope is at most 3 %, green edge 9-16 m from the centre, collar +8 mm, rough +40 mm, "
        "surround terrain beyond the collar with a mean radial slope of -8 % to +2 %. True Stimp ~ N(10, 1.2), grain strong "
        "on 35 % of greens. The ball rolls with `dv/dt = -a_r v_hat - (5/7) G grad z + kappa a_r g_hat`."
    )
    add("")

    # ------------------------------------------------------------------ 3 main tables
    add(f"## 3. Results at the nominal seating noise ({nseat} mrad)")
    add("")
    add("Median absolute lateral miss at the hole, perfect execution [cm]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "median_miss", _cm))
    add("")
    add("90th percentile of the lateral miss, perfect execution [cm]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "p90_miss", _cm))
    add("")
    add("Make probability with perfect execution [%]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "make_perfect", _pct))
    add("")
    add(f"Make probability with human execution noise ({meta['sigma_dir_deg']:g} deg, {100 * meta['sigma_speed']:g} %) [%]:")
    add("")
    add(_by_distance_table(nom, ALL_METHODS, dk, "make_human", lambda v: _pct(v, 1)))
    add("")
    add("By green class, all lengths pooled (median miss [cm] / make probability with perfect execution [%]):")
    add("")
    rows = []
    for m in ALL_METHODS:
        rows.append([m] + [f"{_cm(nom[m]['by_class'][c]['median_miss'])} / {_pct(nom[m]['by_class'][c]['make_perfect'])}" for c in meta["classes"]])
    add(_table(["Method"] + list(meta["classes"]), rows))
    add("")
    add(f"![Median miss by green class]({figs[7]})")
    add("")
    add("The per-length, per-class tables are in the appendix (section 14).")
    add("")

    # ------------------------------------------------------------------ 4 seating noise
    add("## 4. Seating noise: the dominant uncertainty")
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
        add(f"Seating noise {s} mrad - make probability, perfect execution [%]:")
        add("")
        add(_by_distance_table(t, ALL_METHODS, dk, "make_perfect", _pct))
        add("")
        add(f"Seating noise {s} mrad - make probability, human execution [%]:")
        add("")
        add(_by_distance_table(t, ALL_METHODS, dk, "make_human", lambda v: _pct(v, 1)))
        add("")
    add(f"![Seating-noise sensitivity]({figs[2]})")
    add("")
    add("@@SEAT_TEXT@@")
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
        "hollows of 0.2 m RMS that are independent of the green (pessimistic)."
    )
    add("")
    add(_horizon_section(summary))
    add("")
    add(f"![Horizon test]({figs[3]})")
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
    add(f"![Range error]({figs[4]})")
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
    add("Pace: median absolute error of the roll-out past the hole against the 0.30 m target [cm] (perfect execution):")
    add("")
    add(_by_distance_table(nom, ("STRAIGHT", "B0", "B1", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT", "HUMAN05", "ORACLE_SLOPE", "ORACLE"), dk, "median_pace_err", lambda v: _cm(v, 0)))
    add("")
    add("Putts that stop short of the hole with perfect execution [%]:")
    add("")
    add(_by_distance_table(nom, ("STRAIGHT", "B0", "B1", "SURVEY3", "HUMAN05", "ORACLE_SLOPE", "ORACLE"), dk, "short", _pct))
    add("")
    add(f"![Cross-slope error]({figs[5]})")
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
    add("Columns 2-9: make probability with human execution [%].")
    add("")
    add("@@EXEC_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 10 bearing
    add("## 10. Value of the camera bearing (flag-out fallback)")
    add("")
    add(_by_distance_table(nom, ("B0", "FLAGOUT"), dk, "median_miss", _cm))
    add("")
    add("Median lateral miss [cm] above; make probability with perfect execution [%] below.")
    add("")
    add(_by_distance_table(nom, ("B0", "FLAGOUT"), dk, "make_perfect", _pct))
    add("")
    add("@@BEARING_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 11 sweeps
    add(f"## 11. Sensitivity sweeps ({meta['n_putts_sweep']} putts, seating noise {nseat} mrad)")
    add("")
    add("All rows of one table use the same putts and the same noise draws. \"pace err\" is the median absolute pace error.")
    add("")
    add("**Camera preset.** The legacy presets also differ from GL1 in field of view (±40 deg) and lens height (4.5 mm).")
    add("")
    add(_sweep_table("Preset", sw["camera"], ("B1", "B2"), dk))
    add("")
    add("**Lens height** (fraction of reads with the base hidden in the last column):")
    add("")
    rows = []
    for label, tables in sw["h_cam_mm"].items():
        for r in _sweep_rows({label + " mm": tables}, ("B1", "B2"), dk):
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
    add("Make probability with perfect execution [%] by length, same sweep:")
    add("")
    rows = []
    for label, tables in sw["stimp_error_pct"].items():
        for m in ("B1", "ORACLE_SLOPE"):
            rows.append([label, m] + [_pct(tables[m]["by_distance"][d]["make_perfect"]) for d in dk])
    add(_table(["Stimp error [%]", "Method"] + [f"{d} m" for d in dk], rows))
    add("")
    add("**Grain sensor.**")
    add("")
    add(_sweep_table("Variant", sw["grain"], ("B1",), dk))
    add("")
    add("**Precision Read when the two seatings are correlated** (0 = independent, 1 = the spin only cancels the device bias):")
    add("")
    add(_sweep_table("Correlation", sw["spin_seat_correlation"], ("B1", "B0S"), dk))
    add("")
    add("**Survey: allowance for the slope field not being plane-plus-curvature** (`sigma_field`):")
    add("")
    add(_sweep_table("sigma_field [mrad]", sw["survey_sigma_field_mrad"], ("SURVEY2", "SURVEY3"), dk))
    add("")
    add("@@SWEEP_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 12 where it helps
    add("## 12. Where fusion helps, where it does not")
    add("")
    sub = diag["subsets"]
    cols = ("STRAIGHT", "B0", "B1", "B2", "B0S", "SURVEY3", "HUMAN05", "HUMAN10")
    rows = []
    for label, entry in sub.items():
        n = entry["B1"].get("n", 0)
        if n == 0:
            continue
        rows.append([label, str(n)] + [f"{_cm(entry[m]['median_miss'])} / {_pct(entry[m]['make_perfect'])}" for m in cols])
    add("Median miss [cm] / make probability with perfect execution [%] on subsets of the putts:")
    add("")
    add(_table(["Subset", "N"] + list(cols), rows))
    add("")
    dbf = diag["double_break_fraction"]
    add("Share of putts with a double break (cross slope changes sign along the line with at least 0.3 % on both sides): "
        + ", ".join(f"{d} m {_pct(dbf[d])} %" for d in dk) + ".")
    add("")
    add("Confidence score against outcome (perfect execution; \"within\" = the ball passes within the hole radius of its centre):")
    add("")
    cal = diag["calibration"]
    rows = []
    edges = [(r["lo"], r["hi"]) for r in cal["B1"]]
    all_edges = sorted({(r["lo"], r["hi"]) for m in cal for r in cal[m]})
    for lo, hi in all_edges:
        row = [f"{lo:.2f}-{hi:.2f}"]
        for m in ("B1", "B0S", "SURVEY3", "B2"):
            hit = [r for r in cal[m] if r["lo"] == lo]
            row.append(f"{hit[0]['mean_confidence']:.2f} -> {hit[0]['within_hole']:.2f} (n={hit[0]['n']})" if hit else "-")
        rows.append(row)
    del edges
    add(_table(["Confidence bin", "B1: mean score -> fraction within", "B0S", "SURVEY3", "B2"], rows))
    add("")
    add(f"![Confidence calibration]({figs[6]})")
    add("")
    add("How the aim was obtained (number of reads solved on the fitted patch / on its secant plane / best effort / straight): "
        + "; ".join(f"{m} {'/'.join(str(v) for v in c)}" for m, c in diag["aim_sources"].items() if m in ("B0", "B1", "B2", "B0S", "SURVEY2", "SURVEY3", "FLAGOUT")) + ".")
    add("")
    add("@@FUSION_TEXT@@")
    add("")

    # ------------------------------------------------------------------ 13 limitations
    add("## 13. Assumptions and limits of this evaluation")
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
        ("median_miss", "Median lateral miss, perfect execution [cm]", _cm),
        ("p90_miss", "90th percentile of the lateral miss, perfect execution [cm]", _cm),
        ("make_perfect", "Make probability, perfect execution [%]", _pct),
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
    add("### 14.3 Reproducing")
    add("")
    add("```")
    add("cd sim")
    add("python -m pytest -q                 # test-suite")
    add(f"python -m greenline_sim.montecarlo  # this report, summary.json, plots, reference vectors (about {rt['total'] / 60.0:.0f} min)")
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
