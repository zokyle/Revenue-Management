"""A* search kernel of the router.

One function, :func:`search`, written in the subset of Python that numba can
compile.  With numba installed it is JIT-compiled (and cached on disk); without
numba the very same code runs in the interpreter - about two orders of
magnitude slower, which is fine for the small unit tests but not for a real
board.  :data:`HAVE_NUMBA` tells which one is in use.

All costs are integers, and ties in the priority queue are broken by an
insertion counter, so the result is fully deterministic and identical with
and without numba.

Search space
------------
``cost[l, y, x]`` (int32) describes the cells of ``L`` routing layers of a
window of the grid: 0 = the track centre may not be here, otherwise entering
the cell costs the step cost of the move plus ``cost - 1``.

Moves: 8 neighbours on the same layer (a diagonal move additionally needs the
two cells that complete the unit square to be enterable - no corner cutting,
see :mod:`gleda.raster`) and a layer change through a via.

``viamap[y, x]`` (int32): 0 = no via here, :data:`FREE_VIA` (-1) = a via /
plated hole of this net already exists (layer change is free), otherwise a
new via costs ``via_cost + viamap - 1``.

``nv_levels`` > 1 limits the number of NEW vias of the returned path to
``nv_levels - 1`` (the via count becomes part of the search state).

Targets are the cells listed in ``dst`` plus every enterable cell of the
layers whose bit is set in ``tlayers`` ("reach that layer anywhere" - used to
fan a pad out to a via).
"""
from __future__ import annotations

import numpy as np

try:                                                        # pragma: no cover
    from numba import njit
    HAVE_NUMBA = True
except Exception:                                           # pragma: no cover
    HAVE_NUMBA = False

    def njit(*args, **kwargs):
        def wrap(fn):
            return fn
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return wrap

#: ``viamap`` value marking an existing via / plated hole of the routed net
FREE_VIA = -1


@njit(cache=True)
def search(cost, viamap, src, dst, tlayers, step_h, step_v, step_d, via_cost, nv_levels,
           hx0, hy0, hx1, hy1, hnum, hden, max_pops):
    """Cheapest path from any cell of ``src`` to any target cell.

    Parameters
    ----------
    cost      int32[L, H, W]    see module docstring
    viamap    int32[H, W]
    src, dst  int32[n]          cell indices ``(l * H + y) * W + x``
    tlayers   int               bit mask of layers that are targets as a whole
    step_h, step_v, step_d  int32[L]  cost of a horizontal / vertical /
                                diagonal move on each layer
    via_cost  int               cost of a new via
    nv_levels int               1 = unlimited vias, k + 1 = at most k new vias
    hx0..hy1  int               box that contains every target (heuristic);
                                ignored when ``hnum`` is 0
    hnum, hden int              heuristic weight as a fraction (1/1 = admissible)
    max_pops  int               give up after this many expansions (0 = never)

    Returns ``(path, pops)``: ``path`` is an int32 array of cell indices from
    a source cell to a target cell (empty if there is no path).
    """
    L = cost.shape[0]
    H = cost.shape[1]
    W = cost.shape[2]
    HW = H * W
    N = L * HW
    S = N * nv_levels
    INF = 2147483647
    g = np.empty(S, np.int64)
    parent = np.empty(S, np.int32)
    state = np.zeros(S, np.uint8)            # 0 unseen, 1 open, 2 closed
    tflag = np.zeros(N, np.uint8)
    for i in range(dst.shape[0]):
        tflag[dst[i]] = 1

    mo = INF
    md = INF
    for l in range(L):
        if step_h[l] < mo:
            mo = step_h[l]
        if step_v[l] < mo:
            mo = step_v[l]
        if step_d[l] < md:
            md = step_d[l]
    if md > 2 * mo:
        md = 2 * mo

    cap = 1 << 14
    hk = np.empty(cap, np.int64)
    hv = np.empty(cap, np.int32)
    hn = 0
    seq = 0
    SEQMAX = 4294967295

    dxs = np.array([1, -1, 0, 0, 1, 1, -1, -1], np.int32)
    dys = np.array([0, 0, 1, -1, 1, -1, 1, -1], np.int32)

    # ---- sources ----------------------------------------------------------
    for i in range(src.shape[0]):
        c = src[i]
        l = c // HW
        r = c - l * HW
        y = r // W
        x = r - y * W
        if cost[l, y, x] == 0:
            continue
        if state[c] != 0:
            continue
        g[c] = 0
        parent[c] = -1
        state[c] = 1
        h = 0
        if hnum > 0:
            ddx = 0
            if x < hx0:
                ddx = hx0 - x
            elif x > hx1:
                ddx = x - hx1
            ddy = 0
            if y < hy0:
                ddy = hy0 - y
            elif y > hy1:
                ddy = y - hy1
            if ddx > ddy:
                h = mo * (ddx - ddy) + md * ddy
            else:
                h = mo * (ddy - ddx) + md * ddx
            h = h * hnum // hden
        key = np.int64(h) * 4294967296 + (SEQMAX - seq)
        seq += 1
        if hn == cap:
            cap2 = cap * 2
            hk2 = np.empty(cap2, np.int64)
            hv2 = np.empty(cap2, np.int32)
            hk2[:cap] = hk
            hv2[:cap] = hv
            hk = hk2
            hv = hv2
            cap = cap2
        j = hn
        hn += 1
        while j > 0:
            p = (j - 1) >> 1
            if hk[p] <= key:
                break
            hk[j] = hk[p]
            hv[j] = hv[p]
            j = p
        hk[j] = key
        hv[j] = c

    found = -1
    pops = 0
    vm = 0
    ng = 0
    ns = 0
    nx = 0
    ny = 0
    nl = 0
    cc = 0
    nvia = 1
    while hn > 0:
        # ---- pop ----------------------------------------------------------
        s = hv[0]
        hn -= 1
        if hn > 0:
            key = hk[hn]
            val = hv[hn]
            j = 0
            while True:
                a = 2 * j + 1
                if a >= hn:
                    break
                b = a + 1
                if b < hn and hk[b] < hk[a]:
                    a = b
                if hk[a] >= key:
                    break
                hk[j] = hk[a]
                hv[j] = hv[a]
                j = a
            hk[j] = key
            hv[j] = val
        if state[s] == 2:
            continue
        state[s] = 2
        pops += 1
        v = s // N
        c = s - v * N
        l = c // HW
        r = c - l * HW
        y = r // W
        x = r - y * W
        if tflag[c] != 0 or ((tlayers >> l) & 1) != 0:
            found = s
            break
        if max_pops > 0 and pops >= max_pops:
            break
        gs = g[s]
        # ---- same-layer moves and (k == 8) the via ----------------------
        for k in range(9):
            if k < 8:
                nx = x + dxs[k]
                ny = y + dys[k]
                if nx < 0 or ny < 0 or nx >= W or ny >= H:
                    continue
                cc = cost[l, ny, nx]
                if cc == 0:
                    continue
                if k >= 4:
                    if cost[l, y, nx] == 0 or cost[l, ny, x] == 0:
                        continue
                    ng = gs + step_d[l] + cc - 1
                elif k < 2:
                    ng = gs + step_h[l] + cc - 1
                else:
                    ng = gs + step_v[l] + cc - 1
                ns = v * N + (l * H + ny) * W + nx
                nl = l
                nvia = 1
            else:
                vm = viamap[y, x]
                if vm == 0 or L < 2:
                    continue
                nvia = L - 1
            for q in range(nvia):
                if k == 8:
                    nl = q if q < l else q + 1
                    cc = cost[nl, y, x]
                    if cc == 0:
                        continue
                    nx = x
                    ny = y
                    if vm < 0:
                        ng = gs + 1 + cc - 1
                        ns = v * N + (nl * H + y) * W + x
                    else:
                        if nv_levels > 1:
                            if v >= nv_levels - 1:
                                continue
                            ns = (v + 1) * N + (nl * H + y) * W + x
                        else:
                            ns = (nl * H + y) * W + x
                        ng = gs + via_cost + (vm - 1) + cc - 1
                if state[ns] == 2:
                    continue
                if state[ns] == 1 and g[ns] <= ng:
                    continue
                g[ns] = ng
                parent[ns] = s
                state[ns] = 1
                h = 0
                if hnum > 0:
                    ddx = 0
                    if nx < hx0:
                        ddx = hx0 - nx
                    elif nx > hx1:
                        ddx = nx - hx1
                    ddy = 0
                    if ny < hy0:
                        ddy = hy0 - ny
                    elif ny > hy1:
                        ddy = ny - hy1
                    if ddx > ddy:
                        h = mo * (ddx - ddy) + md * ddy
                    else:
                        h = mo * (ddy - ddx) + md * ddx
                    h = h * hnum // hden
                key = np.int64(ng + h) * 4294967296 + (SEQMAX - seq)
                seq += 1
                if hn == cap:
                    cap2 = cap * 2
                    hk2 = np.empty(cap2, np.int64)
                    hv2 = np.empty(cap2, np.int32)
                    hk2[:cap] = hk
                    hv2[:cap] = hv
                    hk = hk2
                    hv = hv2
                    cap = cap2
                j = hn
                hn += 1
                while j > 0:
                    p = (j - 1) >> 1
                    if hk[p] <= key:
                        break
                    hk[j] = hk[p]
                    hv[j] = hv[p]
                    j = p
                hk[j] = key
                hv[j] = ns

    if found < 0:
        return np.empty(0, np.int32), pops
    n = 0
    s = found
    while s >= 0:
        n += 1
        s = parent[s]
    path = np.empty(n, np.int32)
    s = found
    i = n - 1
    while s >= 0:
        path[i] = s % N
        i -= 1
        s = parent[s]
    return path, pops


@njit(cache=True)
def _leg_cost(cost, l, x, y, dx, dy, n, step):
    """Cost of ``n`` moves (dx, dy) from (x, y) on layer ``l``; -1 if a cell
    is blocked or a diagonal move would cut a corner."""
    total = 0
    for _i in range(n):
        nx = x + dx
        ny = y + dy
        c = cost[l, ny, nx]
        if c == 0:
            return -1
        if dx != 0 and dy != 0:
            if cost[l, y, nx] == 0 or cost[l, ny, x] == 0:
                return -1
        total += step + c - 1
        x = nx
        y = ny
    return total


@njit(cache=True)
def smooth(path, cost, step_h, step_v, step_d, lookahead):
    """Straighten a path found by :func:`search` without making it more
    expensive.

    Within each same-layer stretch, a piece of the path is replaced by a
    two-leg connection (one diagonal run and one straight run, in either
    order) between its end cells whenever every cell of that connection is
    enterable and its cost is not higher than the cost of the piece it
    replaces.  Layer changes (vias) stay where they are.  Returns the new
    path (same first and last cell)."""
    L = cost.shape[0]
    H = cost.shape[1]
    W = cost.shape[2]
    HW = H * W
    n = path.shape[0]
    out = np.empty(n, np.int32)
    m = 0
    ls = np.empty(n, np.int32)
    xs = np.empty(n, np.int32)
    ys = np.empty(n, np.int32)
    acc = np.zeros(n, np.int64)                 # cost of the original path up to cell i
    for i in range(n):
        c = path[i]
        l = c // HW
        r = c - l * HW
        ls[i] = l
        ys[i] = r // W
        xs[i] = r - (r // W) * W
        if i > 0 and ls[i] == ls[i - 1]:
            dx = xs[i] - xs[i - 1]
            dy = ys[i] - ys[i - 1]
            if dx != 0 and dy != 0:
                st = step_d[l]
            elif dx != 0:
                st = step_h[l]
            else:
                st = step_v[l]
            acc[i] = acc[i - 1] + st + cost[l, ys[i], xs[i]] - 1
        elif i > 0:
            acc[i] = acc[i - 1]
    i = 0
    out[m] = path[0]
    m += 1
    while i < n - 1:
        if ls[i + 1] != ls[i]:
            i += 1
            out[m] = path[i]
            m += 1
            continue
        l = ls[i]
        e = i + 1
        while e + 1 < n and ls[e + 1] == l:
            e += 1
        jmax = e
        if jmax > i + lookahead:
            jmax = i + lookahead
        done = False
        j = jmax
        while j > i + 1 and not done:
            dx = xs[j] - xs[i]
            dy = ys[j] - ys[i]
            adx = dx if dx >= 0 else -dx
            ady = dy if dy >= 0 else -dy
            sx = 1 if dx > 0 else (-1 if dx < 0 else 0)
            sy = 1 if dy > 0 else (-1 if dy < 0 else 0)
            nd = adx if adx < ady else ady
            no = adx + ady - 2 * nd
            if adx >= ady:
                ox = sx
                oy = 0
                so = step_h[l]
            else:
                ox = 0
                oy = sy
                so = step_v[l]
            if nd + no >= j - i and not (nd > 0 and no > 0):
                # already a single straight run of minimal length
                j -= 1
                continue
            budget = acc[j] - acc[i]
            for variant in range(2):
                if variant == 0:
                    c1 = _leg_cost(cost, l, xs[i], ys[i], sx, sy, nd, step_d[l])
                    if c1 < 0:
                        continue
                    c2 = _leg_cost(cost, l, xs[i] + sx * nd, ys[i] + sy * nd, ox, oy, no, so)
                else:
                    c1 = _leg_cost(cost, l, xs[i], ys[i], ox, oy, no, so)
                    if c1 < 0:
                        continue
                    c2 = _leg_cost(cost, l, xs[i] + ox * no, ys[i] + oy * no, sx, sy, nd,
                                   step_d[l])
                if c2 < 0 or c1 + c2 > budget:
                    continue
                # emit the cells of this connection
                if m + nd + no > out.shape[0]:
                    out2 = np.empty(2 * out.shape[0] + nd + no, np.int32)
                    out2[:m] = out[:m]
                    out = out2
                x = xs[i]
                y = ys[i]
                for k in range(nd + no):
                    first_diag = (variant == 0 and k < nd) or (variant == 1 and k >= no)
                    if first_diag:
                        x += sx
                        y += sy
                    else:
                        x += ox
                        y += oy
                    out[m] = (l * H + y) * W + x
                    m += 1
                i = j
                done = True
                break
            if not done:
                j -= 1
        if not done:
            i += 1
            if m >= out.shape[0]:
                out2 = np.empty(2 * out.shape[0] + 1, np.int32)
                out2[:m] = out[:m]
                out = out2
            out[m] = path[i]
            m += 1
    return out[:m].copy()


__all__ = ["search", "smooth", "HAVE_NUMBA", "FREE_VIA"]
