/**
 * Caddie - shared front-end helpers (plain JS, no framework).
 *
 *   Caddie.api(path, {method, body})   JSON fetch helper; throws Error(detail) on !ok
 *   Caddie.ready(fn)                   run fn(playerId, player) once the current player is resolved
 *   Caddie.getPlayerId() / setPlayerId(id)
 *   Caddie.fmtPct(x) / fmtNum(x, digits) / fmtDate(iso) / signed(x)
 *   Caddie.toast(message, kind)        kind = 'error' | 'success' | 'info'
 *   Caddie.chart(canvasId, config)     Chart.js wrapper that destroys a previous chart on the same canvas
 *   Caddie.esc(text) / el(tag, attrs, children) / $ / $$ / today()
 *   Caddie.clubs() / courses()         cached lists for the current player
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'caddie_player_id';

    // ------------------------------------------------------------------
    // DOM helpers
    // ------------------------------------------------------------------
    const $ = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function el(tag, attrs, children) {
        const node = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach((k) => {
                const v = attrs[k];
                if (v == null || v === false) return;
                if (k === 'class') node.className = v;
                else if (k === 'text') node.textContent = v;
                else if (k === 'html') node.innerHTML = v;
                else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
                else if (k === 'value') node.value = v;
                else if (k === 'checked') node.checked = !!v;
                else node.setAttribute(k, v === true ? '' : v);
            });
        }
        (Array.isArray(children) ? children : (children == null ? [] : [children])).forEach((c) => {
            if (c == null) return;
            node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        });
        return node;
    }

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------
    function isNil(v) { return v === null || v === undefined || (typeof v === 'number' && isNaN(v)); }
    function fmtPct(v, digits) { return isNil(v) ? '–' : (Number(v) * 100).toFixed(digits || 0) + '%'; }
    function fmtNum(v, digits) { return isNil(v) ? '–' : Number(v).toFixed(digits == null ? 1 : digits); }
    function signed(v, digits) {
        if (isNil(v)) return '–';
        const n = Number(v);
        const s = n.toFixed(digits == null ? 1 : digits);
        return n > 0 ? '+' + s : (n === 0 ? 'E' : s);
    }
    function fmtDate(iso) {
        if (!iso) return '–';
        const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    }
    function today() {
        const d = new Date();
        return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    }
    function num(v, fallback) {
        if (v === '' || v === null || v === undefined) return fallback === undefined ? null : fallback;
        const n = Number(v);
        return isNaN(n) ? (fallback === undefined ? null : fallback) : n;
    }

    // ------------------------------------------------------------------
    // Toasts
    // ------------------------------------------------------------------
    function toastRoot() {
        let root = document.getElementById('toast-root');
        if (!root) {
            root = el('div', { id: 'toast-root' });
            document.body.appendChild(root);
        }
        return root;
    }
    function toast(message, kind, ms) {
        kind = kind || 'error';
        const node = el('div', { class: 'toast toast-' + kind, role: 'alert' }, [
            el('span', { text: String(message) }),
            el('button', { type: 'button', 'aria-label': 'Dismiss', text: '×', onclick: () => node.remove() }),
        ]);
        toastRoot().appendChild(node);
        setTimeout(() => node.remove(), ms || (kind === 'error' ? 8000 : 4000));
        return node;
    }

    // ------------------------------------------------------------------
    // Fetch helper
    // ------------------------------------------------------------------
    function detailFrom(data, fallback) {
        if (data == null || data === '') return fallback;
        if (typeof data === 'string') return data.slice(0, 400);
        const d = data.detail !== undefined ? data.detail : data;
        if (typeof d === 'string') return d;
        if (Array.isArray(d)) {
            return d.map((e) => {
                if (e && e.msg) {
                    const loc = (e.loc || []).filter((x) => x !== 'body').join('.');
                    return (loc ? loc + ': ' : '') + e.msg;
                }
                return typeof e === 'string' ? e : JSON.stringify(e);
            }).join('; ');
        }
        try { return JSON.stringify(d).slice(0, 400); } catch (_) { return fallback; }
    }

    async function api(path, opts) {
        opts = opts || {};
        const init = { method: opts.method || 'GET', headers: { Accept: 'application/json' } };
        if (opts.body !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(opts.body);
        }
        let res;
        try {
            res = await fetch(path, init);
        } catch (e) {
            throw new Error('Network error while calling ' + path + ': ' + (e.message || e));
        }
        if (res.status === 204) return null;
        const text = await res.text();
        let data = null;
        if (text) {
            try { data = JSON.parse(text); } catch (_) { data = text; }
        }
        if (!res.ok) {
            const err = new Error(detailFrom(data, res.status + ' ' + res.statusText));
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    }

    // ------------------------------------------------------------------
    // Chart.js defaults + wrapper
    // ------------------------------------------------------------------
    const colors = {
        emerald: 'rgb(16, 185, 129)', emeraldFaded: 'rgba(16, 185, 129, 0.12)',
        green: 'rgb(34, 197, 94)', blue: 'rgb(59, 130, 246)', sky: 'rgb(14, 165, 233)',
        amber: 'rgb(245, 158, 11)', red: 'rgb(239, 68, 68)', rose: 'rgb(244, 63, 94)',
        slate: 'rgb(51, 65, 85)', gray: 'rgb(156, 163, 175)', grayLight: 'rgba(156, 163, 175, 0.25)',
        purple: 'rgb(139, 92, 246)',
    };
    if (window.Chart) {
        Chart.defaults.font.family = "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif";
        Chart.defaults.font.size = 11;
        Chart.defaults.color = '#6b7280';
        Chart.defaults.plugins.legend.display = false;
        Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.9)';
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 8;
    }
    function chart(canvas, config) {
        if (!window.Chart) return null;
        const node = typeof canvas === 'string' ? document.getElementById(canvas) : canvas;
        if (!node) return null;
        const existing = Chart.getChart(node);
        if (existing) existing.destroy();
        return new Chart(node, config);
    }

    // ------------------------------------------------------------------
    // Current player
    // ------------------------------------------------------------------
    const state = { playerId: null, player: null, players: [], booted: false };
    const readyQueue = [];
    const cache = {};

    function getPlayerId() { return state.playerId; }
    function getPlayer() { return state.player; }
    function setPlayerId(id) {
        state.playerId = id ? Number(id) : null;
        try {
            if (id) localStorage.setItem(STORAGE_KEY, String(id));
            else localStorage.removeItem(STORAGE_KEY);
        } catch (_) { /* storage unavailable (private mode) */ }
    }

    async function runSafely(fn) {
        try {
            await fn(state.playerId, state.player);
        } catch (e) {
            console.error(e);
            toast(e && e.message ? e.message : String(e));
        }
    }
    function ready(fn) {
        if (state.booted && state.playerId) runSafely(fn);
        else readyQueue.push(fn);
    }
    function flushQueue() {
        while (readyQueue.length) runSafely(readyQueue.shift());
    }

    function showGate(show) {
        const gate = document.getElementById('player-gate');
        const page = document.getElementById('page-content');
        if (gate) gate.classList.toggle('hidden', !show);
        if (page) page.classList.toggle('hidden', !!show);
        const cancel = document.getElementById('player-gate-cancel');
        if (cancel) cancel.classList.toggle('hidden', !state.players.length);
    }

    function renderSwitcher() {
        document.querySelectorAll('select.player-switcher').forEach((sel) => {
            sel.innerHTML = '';
            state.players.forEach((p) => {
                sel.appendChild(el('option', { value: p.id, text: p.name + ' (' + fmtNum(p.handicap_index, 1) + ')' }));
            });
            sel.appendChild(el('option', { value: '__new', text: '+ New player…' }));
            if (state.playerId) sel.value = String(state.playerId);
            sel.onchange = () => {
                if (sel.value === '__new') { showGate(true); return; }
                setPlayerId(sel.value);
                window.location.reload();
            };
        });
        const header = document.getElementById('header-player');
        if (header) {
            header.textContent = state.player
                ? state.player.name + ' · HCP ' + fmtNum(state.player.handicap_index, 1) + ' · target ' + state.player.target_score
                : 'No player yet';
        }
    }

    function wireGateForm() {
        const form = document.getElementById('player-gate-form');
        if (!form) return;
        form.addEventListener('submit', async (ev) => {
            ev.preventDefault();
            const name = (form.elements.name.value || '').trim();
            const handicap = num(form.elements.handicap_index.value, 15);
            const target = num(form.elements.target_score.value, 79);
            if (!name) { toast('Please enter a name'); return; }
            if (handicap < -10 || handicap > 54) { toast('Handicap should be between -10 and 54'); return; }
            if (target < 55 || target > 150) { toast('Target score should be between 55 and 150'); return; }
            const btn = form.querySelector('button[type=submit]');
            btn.disabled = true;
            try {
                const player = await api('/api/players', {
                    method: 'POST',
                    body: { name, handicap_index: handicap, target_score: Math.round(target), default_bag: true },
                });
                setPlayerId(player.id);
                toast('Welcome, ' + player.name + '! A standard 14-club bag was created.', 'success');
                setTimeout(() => window.location.reload(), 400);
            } catch (e) {
                toast(e.message);
                btn.disabled = false;
            }
        });
        const cancel = document.getElementById('player-gate-cancel');
        if (cancel) cancel.addEventListener('click', () => {
            showGate(false);
            const sel = document.getElementById('player-switcher');
            if (sel && state.playerId) sel.value = String(state.playerId);
        });
    }

    async function boot() {
        let stored = null;
        try { stored = localStorage.getItem(STORAGE_KEY); } catch (_) { /* ignore */ }
        try {
            state.players = await api('/api/players') || [];
        } catch (e) {
            state.players = [];
            toast('Could not load players: ' + e.message);
        }
        let chosen = null;
        if (stored) chosen = state.players.find((p) => String(p.id) === String(stored)) || null;
        if (!chosen && state.players.length) chosen = state.players[0];
        if (chosen) {
            setPlayerId(chosen.id);
            state.player = chosen;
        } else {
            setPlayerId(null);
        }
        state.booted = true;
        renderSwitcher();
        wireGateForm();
        if (chosen) {
            showGate(false);
            flushQueue();
        } else {
            showGate(true);
        }
    }

    // ------------------------------------------------------------------
    // Cached lookups
    // ------------------------------------------------------------------
    async function clubs(force) {
        if (!state.playerId) return [];
        if (!cache.clubs || force) cache.clubs = await api('/api/players/' + state.playerId + '/clubs');
        return cache.clubs;
    }
    async function courses(force) {
        if (!cache.courses || force) cache.courses = await api('/api/courses');
        return cache.courses;
    }

    function scoreClass(score, par) {
        if (score == null) return 'score-none';
        const d = score - par;
        if (d <= -2) return 'score-eagle';
        if (d === -1) return 'score-birdie';
        if (d === 0) return 'score-par';
        if (d === 1) return 'score-bogey';
        return 'score-double';
    }

    window.Caddie = {
        api, getPlayerId, setPlayerId, player: getPlayer, players: () => state.players,
        fmtPct, fmtNum, fmtDate, signed, today, num,
        toast, ready, esc, el, $, $$, chart, colors, clubs, courses, scoreClass, showGate,
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
