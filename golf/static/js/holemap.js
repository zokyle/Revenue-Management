/**
 * Caddie - SVG hole map.
 *
 *   HoleMap.drawHoleMap(svgElement, mapSpec, planTee, options)   - planTee and options are optional
 *
 * mapSpec is the render spec from GET /api/courses/{id}/holes/{n}/geometry (also embedded in
 * every strategy plan as plan.data.holes[i].map):
 *   { number, par, yards, shape, dogleg_at_yards, dogleg_angle_deg,
 *     fairway: {x0, x1, half_width}, rough_half_width, green: {x, width, depth},
 *     features: [{kind, side, start, end, offset, width, label}] }
 *
 * Coordinates are local "yardage book" coordinates: x = yards along the centerline from the tee,
 * y = lateral yards (+ = right of center).  The strip is drawn tee-at-bottom, green-at-top, so
 * x maps to the vertical axis and y to the horizontal axis.
 *
 * planTee (from plan.data.holes[i].tee) adds the aim line, dispersion ellipse and landing dots:
 *   { target_yards, aim_offset_yards, ellipse: {x, y, half_depth, half_width}, landing_points: [{x, y, lie}] }
 */
(function () {
    'use strict';

    const NS = 'http://www.w3.org/2000/svg';
    const LAT_HALF = 60;                       // yards drawn either side of the centerline
    const PLOT_W = 260;                        // px for +-60 yards
    const SX = PLOT_W / (2 * LAT_HALF);        // px per lateral yard
    const MARGIN = { left: 40, right: 8, top: 30, bottom: 24 };
    const LEGEND_H = 24;
    const MIN_HEIGHT = 380;
    const PX_PER_YARD = 0.85;                  // longitudinal scale before the min-height rule

    const LIE_COLORS = {
        fairway: '#15803d', green: '#34d399', fringe: '#4ade80', rough: '#d97706',
        sand: '#facc15', recovery: '#1e293b', trees: '#1e293b', penalty: '#2563eb', water: '#2563eb',
        ob: '#dc2626', tee: '#64748b', deep_rough: '#a16207', native: '#78716c',
    };
    const LIE_LABELS = {
        fairway: 'Fairway', green: 'Green', fringe: 'Fringe', rough: 'Rough', sand: 'Sand',
        recovery: 'Recovery', penalty: 'Penalty', ob: 'OB', tee: 'Tee',
    };
    const FEATURE_STYLES = {
        water: { fill: '#60a5fa', stroke: '#2563eb', opacity: 0.9, rx: 6 },
        creek: { fill: '#93c5fd', stroke: '#2563eb', opacity: 0.9, rx: 2 },
        penalty: { fill: '#fdba74', stroke: '#ea580c', opacity: 0.85, rx: 4 },
        ob: { fill: 'HATCH', stroke: '#dc2626', opacity: 1, rx: 0 },
        bunker: { fill: '#fde68a', stroke: '#d97706', opacity: 0.95, rx: 7 },
        trees: { fill: 'TREES', stroke: '#14532d', opacity: 0.95, rx: 8 },
        deep_rough: { fill: '#8a9a5b', stroke: '#65732f', opacity: 0.8, rx: 4 },
        native: { fill: '#c2b280', stroke: '#8b7d3c', opacity: 0.85, rx: 4 },
    };
    const DEFAULT_FEATURE = { fill: '#cbd5e1', stroke: '#64748b', opacity: 0.8, rx: 4 };
    let counter = 0;

    function svgEl(tag, attrs, text) {
        const node = document.createElementNS(NS, tag);
        if (attrs) Object.keys(attrs).forEach((k) => { if (attrs[k] != null) node.setAttribute(k, attrs[k]); });
        if (text != null) node.textContent = text;
        return node;
    }

    function lieColor(lie) { return LIE_COLORS[lie] || '#9ca3af'; }

    /** Lateral [min, max] ranges (yards) covered by a feature. width >= 60 (or 999) means "to the edge". */
    function lateralRanges(f) {
        const w = f.width == null ? 999 : Number(f.width);
        const near = Number(f.offset || 0);
        const toEdge = w >= 60;
        const far = toEdge ? 999 : near + w;
        switch (f.side) {
            case 'left': return [[-far, -near]];
            case 'right': return [[near, far]];
            case 'both': return [[-far, -near], [near, far]];
            default: {
                const half = toEdge ? 999 : w / 2;
                return [[near - half, near + half]];
            }
        }
    }

    function drawHoleMap(svg, spec, planTee, options) {
        options = options || {};
        if (!svg || !spec) return svg;
        const uid = 'hm' + (++counter);
        const yards = Number(spec.yards) || 400;
        const green = spec.green || { x: yards, width: 30, depth: 30 };
        const fairway = spec.fairway || null;
        const roughHalf = Number(spec.rough_half_width || ((fairway ? fairway.half_width : 17.5) + 15));
        const showLegend = options.legend !== false;
        const showTitle = options.title !== false;

        const xMin = -12;
        const xMax = yards + (green.depth || 30) / 2 + 8;
        const plotH = Math.max(MIN_HEIGHT - MARGIN.top - MARGIN.bottom - (showLegend ? LEGEND_H : 0), Math.round((xMax - xMin) * PX_PER_YARD));
        const W = MARGIN.left + PLOT_W + MARGIN.right;
        const H = MARGIN.top + plotH + MARGIN.bottom + (showLegend ? LEGEND_H : 0);
        const SY = plotH / (xMax - xMin);
        const px = (x) => MARGIN.top + plotH - (x - xMin) * SY;       // along the hole -> vertical
        const py = (y) => MARGIN.left + PLOT_W / 2 + y * SX;          // lateral -> horizontal
        const clampY = (y) => Math.max(-LAT_HALF - 5, Math.min(LAT_HALF + 5, y));

        while (svg.firstChild) svg.removeChild(svg.firstChild);
        svg.setAttribute('xmlns', NS);
        svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        svg.setAttribute('width', W);
        svg.setAttribute('height', H);
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', 'Map of hole ' + (spec.number || '') + ', par ' + spec.par + ', ' + yards + ' yards');
        svg.style.fontFamily = "'Inter', 'Segoe UI', system-ui, sans-serif";

        // ---- defs: patterns, clip, arrow markers
        const defs = svgEl('defs');
        const hatch = svgEl('pattern', { id: uid + '-hatch', width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
        hatch.appendChild(svgEl('rect', { width: 6, height: 6, fill: '#fee2e2' }));
        hatch.appendChild(svgEl('line', { x1: 0, y1: 0, x2: 0, y2: 6, stroke: '#dc2626', 'stroke-width': 2 }));
        defs.appendChild(hatch);
        const trees = svgEl('pattern', { id: uid + '-trees', width: 10, height: 10, patternUnits: 'userSpaceOnUse' });
        trees.appendChild(svgEl('rect', { width: 10, height: 10, fill: '#2f6b3a' }));
        trees.appendChild(svgEl('circle', { cx: 3, cy: 3, r: 2.2, fill: '#1d4d2a' }));
        trees.appendChild(svgEl('circle', { cx: 8, cy: 8, r: 2.2, fill: '#3f8a4c' }));
        defs.appendChild(trees);
        const clip = svgEl('clipPath', { id: uid + '-clip' });
        clip.appendChild(svgEl('rect', { x: MARGIN.left, y: MARGIN.top, width: PLOT_W, height: plotH, rx: 10 }));
        defs.appendChild(clip);
        const arrow = svgEl('marker', { id: uid + '-arrow', viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse' });
        arrow.appendChild(svgEl('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#0f172a' }));
        defs.appendChild(arrow);
        const arrowDog = svgEl('marker', { id: uid + '-arrowdog', viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 5, markerHeight: 5, orient: 'auto' });
        arrowDog.appendChild(svgEl('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#7c2d12' }));
        defs.appendChild(arrowDog);
        svg.appendChild(defs);

        const field = svgEl('g', { 'clip-path': 'url(#' + uid + '-clip)' });
        svg.appendChild(field);

        // ---- ground
        field.appendChild(svgEl('rect', { x: MARGIN.left, y: MARGIN.top, width: PLOT_W, height: plotH, fill: '#eef3e6' }));
        const roughEnd = green.x + (green.depth || 30) / 2 + 4;
        field.appendChild(svgEl('rect', {
            x: py(-roughHalf), y: px(roughEnd), width: 2 * roughHalf * SX, height: px(-6) - px(roughEnd),
            fill: '#86bb6a', rx: 14,
        }));
        if (fairway && fairway.x1 > fairway.x0) {
            field.appendChild(svgEl('rect', {
                x: py(-fairway.half_width), y: px(fairway.x1), width: 2 * fairway.half_width * SX, height: px(fairway.x0) - px(fairway.x1),
                fill: '#b9e08c', rx: 12,
            }));
        }
        // centerline
        field.appendChild(svgEl('line', { x1: py(0), y1: px(0), x2: py(0), y2: px(green.x), stroke: '#ffffff', 'stroke-width': 1, 'stroke-dasharray': '3 6', opacity: 0.7 }));

        // ---- features
        (spec.features || []).forEach((f) => {
            const style = FEATURE_STYLES[f.kind] || DEFAULT_FEATURE;
            const fill = style.fill === 'HATCH' ? 'url(#' + uid + '-hatch)' : (style.fill === 'TREES' ? 'url(#' + uid + '-trees)' : style.fill);
            const start = Number(f.start), end = Number(f.end);
            if (isNaN(start) || isNaN(end) || end <= start) return;
            const ranges = lateralRanges(f);
            ranges.forEach((r, i) => {
                const y0 = clampY(r[0]), y1 = clampY(r[1]);
                if (y1 <= y0) return;
                field.appendChild(svgEl('rect', {
                    x: py(y0), y: px(end), width: (y1 - y0) * SX, height: px(start) - px(end),
                    fill, stroke: style.stroke, 'stroke-width': 1.2, opacity: style.opacity, rx: style.rx,
                }));
                if (i === 0) {
                    const label = f.label || (f.kind === 'ob' ? 'OB' : f.kind.replace('_', ' '));
                    const cx = py((y0 + y1) / 2), cy = (px(start) + px(end)) / 2;
                    const width = (y1 - y0) * SX;
                    const t = svgEl('text', {
                        x: cx, y: cy + 3, 'font-size': 9, 'text-anchor': 'middle', fill: '#111827',
                        stroke: '#ffffff', 'stroke-width': 2.5, 'paint-order': 'stroke', 'font-weight': 600,
                        transform: width < 34 ? 'rotate(-90 ' + cx + ' ' + cy + ')' : null,
                    }, label);
                    field.appendChild(t);
                }
            });
        });

        // ---- green + flag
        field.appendChild(svgEl('ellipse', {
            cx: py(0), cy: px(green.x), rx: Math.max(4, (green.width || 30) / 2 * SX), ry: Math.max(4, (green.depth || 30) / 2 * SY),
            fill: '#c6f6d5', stroke: '#15803d', 'stroke-width': 1.5,
        }));
        field.appendChild(svgEl('line', { x1: py(0), y1: px(green.x), x2: py(0), y2: px(green.x) - 12, stroke: '#111827', 'stroke-width': 1.2 }));
        field.appendChild(svgEl('path', { d: 'M ' + py(0) + ' ' + (px(green.x) - 12) + ' l 8 3 l -8 3 z', fill: '#dc2626' }));

        // ---- tee box
        field.appendChild(svgEl('rect', { x: py(-4), y: px(3), width: 8 * SX, height: px(-3) - px(3), fill: '#334155', rx: 2 }));

        // ---- dogleg annotation
        if (spec.dogleg_at_yards && Number(spec.dogleg_at_yards) > 0 && Number(spec.dogleg_at_yards) < yards) {
            const at = Number(spec.dogleg_at_yards);
            const ang = spec.dogleg_angle_deg == null ? null : Number(spec.dogleg_angle_deg);
            const dir = spec.shape === 'dogleg_left' ? -1 : (spec.shape === 'dogleg_right' ? 1 : ((ang || 0) < 0 ? -1 : 1));
            const y0 = px(at);
            field.appendChild(svgEl('line', { x1: py(-roughHalf), y1: y0, x2: py(roughHalf), y2: y0, stroke: '#7c2d12', 'stroke-width': 1, 'stroke-dasharray': '4 3' }));
            const cx = py(0);
            field.appendChild(svgEl('path', {
                d: 'M ' + cx + ' ' + (y0 + 16) + ' L ' + cx + ' ' + (y0 - 4) + ' Q ' + cx + ' ' + (y0 - 18) + ' ' + (cx + dir * 22) + ' ' + (y0 - 22),
                fill: 'none', stroke: '#7c2d12', 'stroke-width': 2, 'marker-end': 'url(#' + uid + '-arrowdog)',
            }));
            field.appendChild(svgEl('text', {
                x: dir > 0 ? py(-roughHalf) + 4 : py(roughHalf) - 4, y: y0 - 6, 'font-size': 9, fill: '#7c2d12', 'font-weight': 600,
                'text-anchor': dir > 0 ? 'start' : 'end', stroke: '#ffffff', 'stroke-width': 2.5, 'paint-order': 'stroke',
            }, 'Dogleg ' + (dir > 0 ? 'right' : 'left') + (ang ? ' ' + Math.abs(Math.round(ang)) + '°' : '') + ' at ' + Math.round(at)));
        }

        // ---- plan overlays
        if (planTee) {
            const tx = Number(planTee.target_yards), ty = Number(planTee.aim_offset_yards || 0);
            const e = planTee.ellipse;
            if (e && e.half_depth && e.half_width) {
                field.appendChild(svgEl('ellipse', {
                    cx: py(e.y || 0), cy: px(e.x || tx), rx: e.half_width * SX, ry: e.half_depth * SY,
                    fill: 'rgba(16, 185, 129, 0.22)', stroke: '#047857', 'stroke-width': 1.2, 'stroke-dasharray': '5 3',
                }));
            }
            (planTee.landing_points || []).forEach((p) => {
                field.appendChild(svgEl('circle', { cx: py(clampY(p.y)), cy: px(p.x), r: 2.2, fill: lieColor(p.lie), stroke: '#ffffff', 'stroke-width': 0.5, opacity: 0.9 }));
            });
            if (!isNaN(tx)) {
                field.appendChild(svgEl('line', {
                    x1: py(0), y1: px(0), x2: py(ty), y2: px(tx), stroke: '#0f172a', 'stroke-width': 1.6, 'stroke-dasharray': '7 4',
                    'marker-end': 'url(#' + uid + '-arrow)',
                }));
                field.appendChild(svgEl('circle', { cx: py(ty), cy: px(tx), r: 5, fill: 'none', stroke: '#0f172a', 'stroke-width': 1.5 }));
                field.appendChild(svgEl('circle', { cx: py(ty), cy: px(tx), r: 1.5, fill: '#0f172a' }));
            }
        }

        // ---- yardage ticks (left)
        const axis = svgEl('g');
        svg.appendChild(axis);
        for (let d = 50; d <= yards; d += 50) {
            axis.appendChild(svgEl('line', { x1: MARGIN.left - 5, y1: px(d), x2: MARGIN.left, y2: px(d), stroke: '#6b7280', 'stroke-width': 1 }));
            axis.appendChild(svgEl('text', { x: MARGIN.left - 8, y: px(d) + 3, 'font-size': 9, fill: '#6b7280', 'text-anchor': 'end' }, String(d)));
        }
        axis.appendChild(svgEl('line', { x1: MARGIN.left - 5, y1: px(yards), x2: MARGIN.left, y2: px(yards), stroke: '#15803d', 'stroke-width': 1.5 }));
        if (yards % 50 !== 0) axis.appendChild(svgEl('text', { x: MARGIN.left - 8, y: px(yards) + 3, 'font-size': 9, fill: '#15803d', 'text-anchor': 'end', 'font-weight': 700 }, String(yards)));
        axis.appendChild(svgEl('text', { x: MARGIN.left - 8, y: px(0) + 3, 'font-size': 9, fill: '#6b7280', 'text-anchor': 'end' }, 'Tee'));
        svg.appendChild(svgEl('rect', { x: MARGIN.left, y: MARGIN.top, width: PLOT_W, height: plotH, rx: 10, fill: 'none', stroke: '#d1d5db' }));

        // ---- title
        if (showTitle) {
            svg.appendChild(svgEl('text', { x: MARGIN.left, y: 18, 'font-size': 12, 'font-weight': 700, fill: '#111827' },
                options.titleText || ('Hole ' + (spec.number || '') + ' · Par ' + spec.par + ' · ' + yards + ' yds')));
            svg.appendChild(svgEl('text', { x: W - MARGIN.right, y: 18, 'font-size': 9, fill: '#6b7280', 'text-anchor': 'end' }, '±60 yds'));
        }

        // ---- legend
        if (showLegend) {
            const items = [
                ['#b9e08c', 'Fairway'], ['#86bb6a', 'Rough'], ['#c6f6d5', 'Green'], ['#60a5fa', 'Water'],
                ['#fde68a', 'Sand'], ['#2f6b3a', 'Trees'], ['url(#' + uid + '-hatch)', 'OB'],
            ];
            if (planTee) items.push(['rgba(16,185,129,0.4)', '90% ellipse']);
            let x = MARGIN.left;
            const y = H - LEGEND_H + 8;
            const legend = svgEl('g');
            items.forEach((it) => {
                legend.appendChild(svgEl('rect', { x, y, width: 9, height: 9, fill: it[0], stroke: '#9ca3af', 'stroke-width': 0.5, rx: 2 }));
                const t = svgEl('text', { x: x + 12, y: y + 8, 'font-size': 8, fill: '#4b5563' }, it[1]);
                legend.appendChild(t);
                x += 14 + it[1].length * 4.6 + 6;
            });
            svg.appendChild(legend);
        }
        return svg;
    }

    /** Build a render spec from raw hole fields (mirrors HoleGeometry.render_spec) - used by the course editor preview. */
    function specFromHole(h) {
        const yards = Number(h.yards) || 400;
        const fw = Number(h.fairway_width_yards) || 35;
        const greenDepth = Number(h.green_depth_yards) || 30;
        // Mirrors HoleGeometry.has_dogleg: a dogleg shape plus a bend point inside the hole (angle optional).
        const hasDogleg = (h.shape === 'dogleg_left' || h.shape === 'dogleg_right') && h.dogleg_at_yards != null
            && Number(h.dogleg_at_yards) > 0 && Number(h.dogleg_at_yards) < yards;
        return {
            number: h.number, par: Number(h.par) || 4, yards, shape: h.shape || 'straight',
            dogleg_at_yards: hasDogleg ? Number(h.dogleg_at_yards) : null,
            dogleg_angle_deg: hasDogleg && h.dogleg_angle_deg != null ? Number(h.dogleg_angle_deg) : null,
            fairway: { x0: Number(h.fairway_start_yards) || 100, x1: yards - greenDepth / 2, half_width: fw / 2 },
            rough_half_width: fw / 2 + (Number(h.rough_width_yards) || 15),
            green: { x: yards, width: Number(h.green_width_yards) || 30, depth: greenDepth },
            features: (h.features || []).map((f) => ({
                kind: f.kind, side: f.side, start: Number(f.start_yards), end: Number(f.end_yards),
                offset: Number(f.offset_yards), width: Math.min(Number(f.width_yards == null ? 999 : f.width_yards), 60), label: f.label || null,
            })),
        };
    }

    window.HoleMap = { drawHoleMap, specFromHole, lieColor, LIE_COLORS, LIE_LABELS, FEATURE_STYLES };
})();
