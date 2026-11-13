"""Small 2D drafting layer on matplotlib for the GL-1 drawings (A3 sheets in millimetres).

A Sheet is one page; a View maps model 2D coordinates to the page (origin + scale) and draws projected edges,
section fills, dimension lines with arrowheads, leaders, ordinate (level) dimensions and centre lines.
Geometry always comes from the CAD solids (geom.hlr / geom.section_polys); dimension values are computed from the
coordinates passed in, never typed.
"""
from __future__ import annotations
import datetime, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch, Polygon as MplPolygon, Rectangle
from matplotlib.path import Path
import geom as G

matplotlib.rcParams["hatch.linewidth"] = 0.22
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["font.family"] = "DejaVu Sans"

MM = 1 / 25.4
PT = 0.3528                     # mm per point
DRAWING_REV = "D-EVT1.2"      # .1: regenerated on the amended rev D YAML (decisions N1 to N10, amendments E8 to E16)
                              # .2: after the review of .1 (GL1-011 gauge-plate detail and legend spacing, GL1-012, GL1-050 item 3 and trims, die cuts GL1-034 / -035)
LW_VIS, LW_THIN, LW_DIM = 0.75, 0.35, 0.3
C_DIM = "#1a3f8f"


def fmt(v, nd=3):
    """Dimension text (magnitude): up to nd decimals, trailing zeros removed, at least one decimal when nd > 0."""
    s = f"{abs(v) + 1e-9:.{nd}f}"
    if "." in s:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def co(v, nd=3):
    """Signed coordinate text."""
    return ("-" if v < -1e-9 else "") + fmt(v, nd)


def geom_path(geom):
    """shapely (Multi)Polygon -> matplotlib compound Path."""
    verts, codes = [], []
    polys = list(getattr(geom, "geoms", [geom]))
    for pg in polys:
        if pg.is_empty or pg.geom_type != "Polygon":
            continue
        for ring in [pg.exterior] + list(pg.interiors):
            xy = np.asarray(ring.coords)
            verts.extend(xy.tolist()); codes.extend([Path.MOVETO] + [Path.LINETO] * (len(xy) - 2) + [Path.CLOSEPOLY])
    return Path(np.array(verts), codes) if verts else None


def spread(targets, gap, lo=None, hi=None):
    """Positions for a sorted list of target coordinates so that neighbours are at least `gap` apart, the block stays
    centred on its targets and inside [lo, hi] where possible."""
    t = list(targets)
    n = len(t)
    if n == 0:
        return t
    for i in range(1, n):
        t[i] = max(t[i], t[i - 1] + gap)
    sh = sum(a - b for a, b in zip(t, targets)) / n
    t = [a - sh for a in t]
    if lo is not None and t[0] < lo:
        t[0] = lo
    for i in range(1, n):
        t[i] = max(t[i], t[i - 1] + gap)
    if hi is not None and t[-1] > hi:
        t[-1] = hi
        for i in range(n - 2, -1, -1):
            t[i] = min(t[i], t[i + 1] - gap)
    return t


class Sheet:
    W, H, B = 420.0, 297.0, 10.0
    TB_W, TB_H = 150.0, 46.0

    def __init__(self, number, title, sheet, n_sheets, part="", material="", process="", tolerance="", scale="", params_rev=""):
        self.number, self.title = number, title
        self.fig = plt.figure(figsize=(self.W * MM, self.H * MM))
        ax = self.ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, self.W); ax.set_ylim(0, self.H); ax.set_aspect("equal"); ax.axis("off")
        B = self.B
        ax.add_patch(Rectangle((B, B), self.W - 2 * B, self.H - 2 * B, fill=False, lw=0.9, ec="k"))
        # title block
        x0, y0, w, h = self.W - B - self.TB_W, B, self.TB_W, self.TB_H
        ax.add_patch(Rectangle((x0, y0), w, h, fc="white", ec="k", lw=0.9, zorder=50))
        rows = [y0 + 9, y0 + 18, y0 + 27, y0 + 36]
        for yy in rows:
            ax.plot([x0, x0 + w], [yy, yy], color="k", lw=0.4, zorder=51)
        ax.plot([x0 + 75, x0 + 75], [y0, rows[2]], color="k", lw=0.4, zorder=51)
        ax.plot([x0 + 112, x0 + 112], [y0, rows[0]], color="k", lw=0.4, zorder=51)

        def cell(x, y, label, value, fs=7.5, bold=False):
            ax.text(x0 + x + 1.2, y + 7.3, label, fontsize=4.3, color="#444", va="top", ha="left", zorder=52)
            ax.text(x0 + x + 1.2, y + 1.5, value, fontsize=fs, va="bottom", ha="left", zorder=52, fontweight="bold" if bold else "normal")
        cell(0, rows[3], "TITLE", f"{number}  {title}", fs=9.5, bold=True)
        cell(0, rows[2], "PROJECT / PART", f"GreenLine GL-1 electronic ball marker  -  {part}", fs=7.0)
        cell(0, rows[1], "MATERIAL / FINISH", material, fs=6.2)
        cell(75, rows[1], "PROCESS", process, fs=6.2)
        cell(0, rows[0], "GENERAL TOLERANCE", tolerance, fs=6.0)
        cell(75, rows[0], "SCALE (A3) / UNITS", f"{scale}   mm", fs=6.5)
        cell(0, y0, "STATUS", "PROVISIONAL - not released", fs=7.8, bold=True)
        cell(75, y0, "DWG REV / PARAMS", f"{DRAWING_REV} / {params_rev}", fs=6.5)
        cell(112, y0, "SHEET / DATE", f"{sheet} of {n_sheets}   {datetime.date.today().isoformat()}", fs=6.0)
        ax.text(B + 2, B + 1.6, "Generated from the CAD model by cad/drawings.py - dimensions are nominal model values, computed, not typed. "
                "Frame: origin at puck centre on the base plane, +x right, +y toward the visor, +z up.",
                fontsize=4.6, color="#333", va="bottom", ha="left")

    def view(self, origin, scale, title=None, title_xy=None):
        v = View(self.ax, origin, scale)
        if title:
            x, y = title_xy if title_xy else (origin[0], origin[1])
            self.ax.text(x, y, title, fontsize=8.5, fontweight="bold", va="bottom", ha="left")
        return v

    def note(self, x, y, lines, fs=6.3, title=None, lh=None, color="k"):
        lh = lh or fs * PT * 1.45
        if title:
            self.ax.text(x, y, title, fontsize=fs + 1.2, fontweight="bold", va="top", ha="left"); y -= lh * 1.25
        for i, ln in enumerate(lines):
            self.ax.text(x, y - i * lh, ln, fontsize=fs, va="top", ha="left", color=color)
        return y - len(lines) * lh

    def table(self, x, y, rows, col_w, fs=5.8, row_h=3.9, header=True):
        """Simple ruled table; rows = list of lists of str; returns the y below the table."""
        ax = self.ax
        tw = sum(col_w)
        for i, r in enumerate(rows):
            yy = y - (i + 1) * row_h
            if header and i == 0:
                ax.add_patch(Rectangle((x, yy), tw, row_h, fc="#e6e9ef", ec="none"))
            cx = x
            for c, wdt in zip(r, col_w):
                ax.text(cx + 0.9, yy + row_h / 2, str(c), fontsize=fs, va="center", ha="left", fontweight="bold" if header and i == 0 else "normal")
                cx += wdt
            ax.plot([x, x + tw], [yy, yy], color="k", lw=0.25)
        ax.add_patch(Rectangle((x, y - len(rows) * row_h), tw, len(rows) * row_h, fill=False, ec="k", lw=0.5))
        cx = x
        for wdt in col_w[:-1]:
            cx += wdt
            ax.plot([cx, cx], [y, y - len(rows) * row_h], color="k", lw=0.25)
        return y - len(rows) * row_h


class View:
    def __init__(self, ax, origin, scale):
        self.ax, self.o, self.s = ax, np.array(origin, float), float(scale)

    # ---- transforms
    def P(self, p):
        return np.asarray(p, float) * self.s + self.o

    def X(self, x):
        return x * self.s + self.o[0]

    def Y(self, y):
        return y * self.s + self.o[1]

    # ---- geometry
    def lines(self, polylines, lw=LW_VIS, color="k", ls="-", zorder=5, alpha=1.0):
        segs = [self.P(p) for p in polylines if len(p) >= 2]
        if segs:
            self.ax.add_collection(LineCollection(segs, linewidths=lw, colors=color, linestyles=ls, zorder=zorder, alpha=alpha, capstyle="round"))

    def hlr(self, shapes, view, hidden=False, lw=LW_VIS, color="k", zorder=5, chord_tol=0.01):
        h = G.hlr(shapes, view, chord_tol=chord_tol, hidden=hidden)
        if hidden:
            self.lines(h["hidden"], lw=0.28, color="#666", ls=(0, (4, 2.5)), zorder=zorder - 1)
        self.lines(h["visible"], lw=lw, color=color, zorder=zorder)
        return h

    def fill(self, geom, fc="#cccccc", ec="k", hatch=None, lw=0.5, zorder=3, alpha=1.0, hatch_color="#555"):
        path = geom_path(geom)
        if path is None:
            return
        path = Path(self.P(path.vertices), path.codes)
        self.ax.add_patch(PathPatch(path, fc=fc, ec="none", lw=0, zorder=zorder, alpha=alpha))
        if hatch:
            self.ax.add_patch(PathPatch(path, fc="none", ec=hatch_color, lw=0, hatch=hatch, zorder=zorder + 0.1))
        self.ax.add_patch(PathPatch(path, fc="none", ec=ec, lw=lw, zorder=zorder + 0.2))

    def circle(self, c, r, lw=LW_THIN, color="k", ls="-", zorder=5):
        t = np.linspace(0, 2 * math.pi, 181)
        self.lines([np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]], lw=lw, color=color, ls=ls, zorder=zorder)

    def centerline(self, a, b, ext=2.0, color="#b02020", lw=0.3, zorder=6):
        a, b = self.P(a), self.P(b)
        d = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        a, b = a - d * ext, b + d * ext
        self.ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, ls=(0, (12, 2.5, 2, 2.5)), zorder=zorder)

    def cross(self, c, size=3.0, **kw):
        cx, cy = c
        self.centerline((cx - size / self.s, cy), (cx + size / self.s, cy), ext=0, **kw)
        self.centerline((cx, cy - size / self.s), (cx, cy + size / self.s), ext=0, **kw)

    # ---- annotation primitives (page coordinates)
    def _arrow(self, tip, direction, size=2.1, color=C_DIM, zorder=20):
        d = np.asarray(direction, float); d /= np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        tip = np.asarray(tip, float)
        pts = [tip, tip - d * size + n * size * 0.17, tip - d * size - n * size * 0.17]
        self.ax.add_patch(MplPolygon(pts, closed=True, fc=color, ec=color, lw=0.1, zorder=zorder))

    def _text(self, xy, s, fs=6.8, ha="center", va="center", rot=0, color=C_DIM, zorder=30, box=True, weight="normal"):
        self.ax.text(xy[0], xy[1], s, fontsize=fs, ha=ha, va=va, rotation=rot, color=color, zorder=zorder, fontweight=weight,
                     bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9) if box else None)

    def dim_h(self, x1, x2, y1, y2, off, text=None, prefix="", suffix="", fs=6.8, nd=3, text_side="auto", gap=0.8, at=None):
        """Horizontal dimension between model x1 and x2. Extension lines start at (x1, y1), (x2, y2); the dimension line is
        `off` page-mm above (off > 0) or below (off < 0) the further feature point."""
        if x2 < x1:
            x1, x2, y1, y2 = x2, x1, y2, y1
        X1, X2, Y1, Y2 = self.X(x1), self.X(x2), self.Y(y1), self.Y(y2)
        yd = at if at is not None else ((max(Y1, Y2) + off) if off > 0 else (min(Y1, Y2) + off))
        ax = self.ax
        for Xa, Ya in ((X1, Y1), (X2, Y2)):
            sg = 1 if yd >= Ya else -1
            ax.plot([Xa, Xa], [Ya + sg * gap, yd + sg * 1.2], color=C_DIM, lw=LW_DIM, zorder=19)
        s = prefix + (text if text is not None else fmt(x2 - x1, nd)) + suffix
        tw = len(s) * fs * PT * 0.62 + 1.5
        span = X2 - X1
        if span >= tw + 5.0:
            ax.plot([X1, X2], [yd, yd], color=C_DIM, lw=LW_DIM, zorder=19)
            self._arrow((X1, yd), (-1, 0)); self._arrow((X2, yd), (1, 0))
            self._text((0.5 * (X1 + X2), yd + 0.2), s, fs, va="center")
        else:                                              # arrows outside, text beside
            side = text_side if text_side in ("left", "right") else "right"
            ax.plot([X1 - 4.2, X2 + 4.2], [yd, yd], color=C_DIM, lw=LW_DIM, zorder=19)
            self._arrow((X1, yd), (1, 0)); self._arrow((X2, yd), (-1, 0))
            if side == "right":
                ax.plot([X2 + 4.2, X2 + 5.2], [yd, yd], color=C_DIM, lw=LW_DIM, zorder=19)
                self._text((X2 + 5.6, yd), s, fs, ha="left")
            else:
                ax.plot([X1 - 5.2, X1 - 4.2], [yd, yd], color=C_DIM, lw=LW_DIM, zorder=19)
                self._text((X1 - 5.6, yd), s, fs, ha="right")
        return yd

    def dim_v(self, y1, y2, x1, x2, off, text=None, prefix="", suffix="", fs=6.8, nd=3, text_side="auto", gap=0.8, at=None):
        """Vertical dimension between model y1 and y2; dimension line `off` page-mm right (off > 0) or left of the features."""
        if y2 < y1:
            y1, y2, x1, x2 = y2, y1, x2, x1
        Y1, Y2, X1, X2 = self.Y(y1), self.Y(y2), self.X(x1), self.X(x2)
        xd = at if at is not None else ((max(X1, X2) + off) if off > 0 else (min(X1, X2) + off))
        ax = self.ax
        for Xa, Ya in ((X1, Y1), (X2, Y2)):
            sg = 1 if xd >= Xa else -1
            ax.plot([Xa + sg * gap, xd + sg * 1.2], [Ya, Ya], color=C_DIM, lw=LW_DIM, zorder=19)
        s = prefix + (text if text is not None else fmt(y2 - y1, nd)) + suffix
        tw = len(s) * fs * PT * 0.62 + 1.5
        span = Y2 - Y1
        if span >= tw + 5.0:
            ax.plot([xd, xd], [Y1, Y2], color=C_DIM, lw=LW_DIM, zorder=19)
            self._arrow((xd, Y1), (0, -1)); self._arrow((xd, Y2), (0, 1))
            self._text((xd - 0.2, 0.5 * (Y1 + Y2)), s, fs, rot=90)
        else:
            ax.plot([xd, xd], [Y1 - 4.2, Y2 + 4.2], color=C_DIM, lw=LW_DIM, zorder=19)
            self._arrow((xd, Y1), (0, 1)); self._arrow((xd, Y2), (0, -1))
            side = text_side if text_side in ("above", "below", "right", "left") else "right"
            if side == "above":
                self._text((xd, Y2 + 5.0), s, fs, va="bottom")
            elif side == "below":
                self._text((xd, Y1 - 5.0), s, fs, va="top")
            elif side == "left":
                self._text((xd - 1.2, 0.5 * (Y1 + Y2)), s, fs, ha="right")
            else:
                self._text((xd + 1.2, 0.5 * (Y1 + Y2)), s, fs, ha="left")
        return xd

    def leader(self, p, text, dx, dy, fs=6.5, ha=None, color="k", dot=True, arrow=False, shelf=3.0, weight="normal"):
        """Leader from model point p to a text placed (dx, dy) page-mm away, with a short horizontal shelf."""
        a = self.P(p)
        b = a + np.array([dx, dy])
        ha = ha or ("left" if dx >= 0 else "right")
        sh = shelf if ha == "left" else -shelf
        self.ax.plot([a[0], b[0], b[0] + sh], [a[1], b[1], b[1]], color=color, lw=0.3, zorder=21)
        if arrow:
            self._arrow(a, a - b, size=1.8, color=color, zorder=22)
        elif dot:
            self.ax.plot([a[0]], [a[1]], marker="o", ms=1.5, color=color, zorder=22)
        self._text((b[0] + sh + (0.6 if ha == "left" else -0.6), b[1]), text, fs, ha=ha, color=color, weight=weight)

    def dia(self, c, r, ang_deg, off=10.0, text=None, fs=6.8, prefix="Ø", nd=3):
        """Diameter call-out: arrow on the circle at ang_deg, text `off` page-mm further out along the same direction."""
        a = math.radians(ang_deg)
        d = np.array([math.cos(a), math.sin(a)])
        p = self.P((c[0] + r * d[0], c[1] + r * d[1]))
        q = p + d * off
        self.ax.plot([p[0], q[0]], [p[1], q[1]], color=C_DIM, lw=LW_DIM, zorder=19)
        self._arrow(p, -d)
        ha = "left" if d[0] >= 0 else "right"
        sh = 2.5 if ha == "left" else -2.5
        self.ax.plot([q[0], q[0] + sh], [q[1], q[1]], color=C_DIM, lw=LW_DIM, zorder=19)
        self._text((q[0] + sh + (0.5 if ha == "left" else -0.5), q[1]), text or (prefix + fmt(2 * r, nd)), fs, ha=ha)

    def levels(self, items, x_model, side="right", x_text=None, fs=6.3, min_gap=3.3, tick=2.0, unit_prefix="z ", color=C_DIM, y_min=None, y_max=None):
        """Ordinate (level) dimensions: items = [(level, label)]; a tick at each level on the vertical line x_model and a
        text column that is spread so that neighbouring texts never overlap (leaders join text and tick)."""
        sg = 1 if side == "right" else -1
        xl = self.X(x_model)
        xt = x_text if x_text is not None else xl + sg * 14.0
        items = sorted(items, key=lambda t: t[0])
        ys = [self.Y(z) for z, _ in items]
        ty = spread(ys, min_gap, y_min, y_max)
        self.ax.plot([xl, xl], [min(ys) - 1.5, max(ys) + 1.5], color=color, lw=LW_DIM, zorder=19)
        for (z, lab), y, t in zip(items, ys, ty):
            self.ax.plot([xl - sg * tick * 0.5, xl + sg * tick, xt - sg * 1.0], [y, y, t], color=color, lw=LW_DIM, zorder=19)
            s = f"{unit_prefix}{co(z)}" + (f"   {lab}" if lab else "")
            self._text((xt, t), s, fs, ha="left" if sg > 0 else "right", color=color)

    def label_column(self, items, x_text, side="right", fs=6.3, min_gap=3.4, color="k", y_min=None, y_max=None, va="center"):
        """Part labels: items = [(model point, text)]; texts in one column at page x_text, spread without overlap."""
        sg = 1 if side == "right" else -1
        items = sorted(items, key=lambda t: self.P(t[0])[1])
        ys = [self.P(p)[1] for p, _ in items]
        ty = spread(ys, min_gap, y_min, y_max)
        for (p, s), t in zip(items, ty):
            a = self.P(p)
            self.ax.plot([a[0], x_text - sg * 4.0, x_text - sg * 0.8], [a[1], t, t], color=color, lw=0.3, zorder=21)
            self.ax.plot([a[0]], [a[1]], marker="o", ms=1.4, color=color, zorder=22)
            self._text((x_text, t), s, fs, ha="left" if sg > 0 else "right", color=color, va=va)

    def view_arrow(self, p, direction, label, length=9.0, fs=9):
        """Viewing-direction arrow at model point p (page-space direction)."""
        a = self.P(p); d = np.asarray(direction, float); d /= np.linalg.norm(d)
        tail = a - d * length
        self.ax.plot([tail[0], a[0]], [tail[1], a[1]], color="k", lw=0.8, zorder=25)
        self._arrow(a, d, size=3.2, color="k", zorder=26)
        self._text(tail - d * 2.5, label, fs, color="k", weight="bold", box=False)

    def cut_line(self, a, b, label, ext=6.0, arrow_dir=(1, 0), fs=9):
        """Section cutting-plane line between model points a and b, with view arrows and letters at both ends."""
        A, B = self.P(a), self.P(b)
        d = (B - A) / np.linalg.norm(B - A)
        A2, B2 = A - d * ext, B + d * ext
        self.ax.plot([A2[0], B2[0]], [A2[1], B2[1]], color="#b02020", lw=0.5, ls=(0, (14, 2.5, 2, 2.5)), zorder=24)
        ad = np.asarray(arrow_dir, float); ad /= np.linalg.norm(ad)
        for q in (A2, B2):
            self.ax.plot([q[0], q[0] + ad[0] * 6], [q[1], q[1] + ad[1] * 6], color="k", lw=0.9, zorder=25)
            self._arrow(q + ad * 6, ad, size=3.0, color="k", zorder=26)
            self._text(q + ad * 3.0 + np.array([-ad[1], ad[0]]) * 3.2 * (1 if q is B2 else -1), label, fs, color="k", weight="bold", box=False)

    def label_row(self, items, y_page, x0, x1, fs=6.2, above=True, color="k"):
        """Part labels in one horizontal row at page y_page between page x0 and x1 (sorted by x, evenly spaced)."""
        items = sorted(items, key=lambda t: self.P(t[0])[0])
        n = len(items)
        for i, (p, s) in enumerate(items):
            a = self.P(p)
            xs = x0 + (i + 0.5) * (x1 - x0) / n
            self.ax.plot([a[0], xs], [a[1], y_page - (1.6 if above else -1.6)], color=color, lw=0.3, zorder=21)
            self.ax.plot([a[0]], [a[1]], marker="o", ms=1.4, color=color, zorder=22)
            self._text((xs, y_page), s, fs, ha="center", va="bottom" if above else "top", color=color)

    def frame(self, x0, y0, x1, y1, label=None, fs=8.5, color="#b02020"):
        """Dash-dot rectangle in model coordinates (detail boundary)."""
        a, b = self.P((x0, y0)), self.P((x1, y1))
        self.ax.add_patch(Rectangle(a, b[0] - a[0], b[1] - a[1], fill=False, ec=color, lw=0.45, ls=(0, (10, 2, 2, 2)), zorder=24))
        if label:
            self._text((b[0] + 1.0, b[1] + 1.0), label, fs, ha="left", va="bottom", color=color, weight="bold", box=False)
