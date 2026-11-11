"""Quick matplotlib picture of a design with routed tracks - a debugging aid
for the router (the real renders come from KiCad via :mod:`gleda.outputs`).

    from gleda import routeplot
    routeplot.plot(design, result.tracks, result.vias, "routing.png")

Top copper is red, bottom copper blue, inner layers green / orange; pads are
drawn filled (top) or hatched outlines (bottom).  The view is from the top,
+y up, exactly the design coordinate system.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from . import geometry
from .model import Design, Track, Via

LAYER_COLOURS = {"F.Cu": "#c83232", "B.Cu": "#3250c8", "In1.Cu": "#32a032",
                 "In2.Cu": "#c88c32"}


def plot(design: Design, tracks: Sequence[Track] = (), vias: Sequence[Via] = (),
         path: str = "routing.png", *, window: Optional[Tuple[float, float, float, float]] = None,
         dpi: int = 200, size: float = 12.0, labels: bool = False,
         marks: Sequence[Tuple[float, float]] = ()) -> str:
    """Write a PNG (or any matplotlib format) of the board.  ``window`` is
    (xmin, ymin, xmax, ymax) in design mm for a close-up; ``marks`` are
    points to circle (e.g. DRC marker positions)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon, Circle as MplCircle

    fig, ax = plt.subplots(figsize=(size, size))
    outline = geometry.outline_polygon(design.outline)
    b = window or outline.bounds
    xs, ys = outline.exterior.xy
    ax.plot(xs, ys, color="black", linewidth=0.8)
    for ring in outline.interiors:
        xs, ys = ring.xy
        ax.plot(xs, ys, color="black", linewidth=0.8)
    for ko in design.keepouts:
        if not (ko.tracks or ko.vias):
            continue
        poly = geometry.keepout_polygon(ko)
        xs, ys = poly.exterior.xy
        ax.plot(xs, ys, color="#888888", linewidth=0.5, linestyle="--")
    for pad in geometry.placed_pads(design):
        if pad.polygon is None:
            ax.add_patch(MplCircle((pad.x, pad.y), pad.drill / 2.0, fill=False, color="black"))
            continue
        top = "F.Cu" in pad.layers
        colour = LAYER_COLOURS["F.Cu" if top else "B.Cu"]
        ax.add_patch(MplPolygon(list(pad.polygon.exterior.coords), closed=True,
                                facecolor=colour if top else "none", edgecolor=colour,
                                alpha=0.45 if top else 0.9, linewidth=0.4))
        if labels and b[0] <= pad.x <= b[2] and b[1] <= pad.y <= b[3]:
            ax.text(pad.x, pad.y, "%s\n%s" % (pad.key, pad.net or "-"), fontsize=2.5,
                    ha="center", va="center", clip_on=True)
    # true scale: set the view first, then ask matplotlib how many points one mm is
    ax.set_aspect("equal")
    ax.set_xlim(b[0] - 0.5, b[2] + 0.5)
    ax.set_ylim(b[1] - 0.5, b[3] + 0.5)
    fig.canvas.draw()
    p0 = ax.transData.transform((0.0, 0.0))
    p1 = ax.transData.transform((1.0, 0.0))
    pt_per_mm = abs(p1[0] - p0[0]) * 72.0 / fig.dpi
    for layer in ("B.Cu", "In2.Cu", "In1.Cu", "F.Cu"):
        for t in tracks:
            if t.layer != layer:
                continue
            ax.plot([t.x1, t.x2], [t.y1, t.y2], color=LAYER_COLOURS.get(layer, "gray"),
                    linewidth=max(0.2, t.width * pt_per_mm), solid_capstyle="round",
                    alpha=0.8)
    for v in vias:
        ax.add_patch(MplCircle((v.x, v.y), v.diameter / 2.0, facecolor="#404040",
                               edgecolor="none", alpha=0.8))
        ax.add_patch(MplCircle((v.x, v.y), v.drill / 2.0, facecolor="white", edgecolor="none"))
    for (mx, my) in marks:
        ax.add_patch(MplCircle((mx, my), 0.6, fill=False, color="magenta", linewidth=1.0))
    ax.set_title("%s: %d tracks, %d vias" % (design.name, len(tracks), len(vias)), fontsize=8)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


__all__ = ["plot", "LAYER_COLOURS"]
