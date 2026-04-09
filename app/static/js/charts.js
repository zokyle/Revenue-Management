/**
 * RevOps Revenue Management - Chart.js Initialization Module
 * Uses Chart.js v4 API. All functions register/destroy existing charts
 * on the same canvas to allow HTMX-driven re-renders.
 */

/* ---------- Shared Defaults ---------- */
const CHART_COLORS = {
    blue:       'rgb(59, 130, 246)',
    blueFaded:  'rgba(59, 130, 246, 0.15)',
    emerald:    'rgb(16, 185, 129)',
    emeraldFaded: 'rgba(16, 185, 129, 0.10)',
    purple:     'rgb(139, 92, 246)',
    amber:      'rgb(245, 158, 11)',
    red:        'rgb(239, 68, 68)',
    gray:       'rgb(156, 163, 175)',
    grayLight:  'rgba(156, 163, 175, 0.2)',
};

const FONT_FAMILY = "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif";

Chart.defaults.font.family = FONT_FAMILY;
Chart.defaults.font.size = 11;
Chart.defaults.color = '#6b7280';
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 42, 0.9)';
Chart.defaults.plugins.tooltip.titleFont = { size: 12, weight: '600' };
Chart.defaults.plugins.tooltip.bodyFont = { size: 11 };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.displayColors = true;
Chart.defaults.plugins.tooltip.boxPadding = 4;

/** Destroy existing chart on a canvas element if present */
function destroyIfExists(canvasId) {
    const existing = Chart.getChart(canvasId);
    if (existing) existing.destroy();
}

/* ==========================================================================
   initRevParChart  --  30-day RevPAR trend (line chart)
   canvasId : string
   labels   : string[]
   actual   : (number|null)[]   -- past actuals, null for future
   forecast : (number|null)[]   -- future forecast, null for past
   ========================================================================== */
function initRevParChart(canvasId, labels, actual, forecast) {
    destroyIfExists(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Actual RevPAR',
                    data: actual,
                    borderColor: CHART_COLORS.blue,
                    backgroundColor: CHART_COLORS.blueFaded,
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: CHART_COLORS.blue,
                    spanGaps: false
                },
                {
                    label: 'Forecast RevPAR',
                    data: forecast,
                    borderColor: CHART_COLORS.blue,
                    borderWidth: 2,
                    borderDash: [6, 4],
                    backgroundColor: 'rgba(59, 130, 246, 0.06)',
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: CHART_COLORS.blue,
                    spanGaps: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            if (ctx.parsed.y === null) return null;
                            return ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 10, font: { size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(v) { return '$' + v; }
                    }
                }
            }
        }
    });
}

/* ==========================================================================
   initForecastChart  --  Actual vs Forecast occupancy with confidence band
   canvasId : string
   labels   : string[]
   actual   : (number|null)[]
   forecast : (number|null)[]
   lower    : (number|null)[]
   upper    : (number|null)[]
   ========================================================================== */
function initForecastChart(canvasId, labels, actual, forecast, lower, upper) {
    destroyIfExists(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Upper Bound',
                    data: upper,
                    borderColor: 'transparent',
                    backgroundColor: 'rgba(59, 130, 246, 0.10)',
                    fill: '+1',           // fill down to next dataset (Lower Bound)
                    pointRadius: 0,
                    tension: 0.3,
                    spanGaps: false,
                    order: 3
                },
                {
                    label: 'Lower Bound',
                    data: lower,
                    borderColor: 'transparent',
                    backgroundColor: 'transparent',
                    fill: false,
                    pointRadius: 0,
                    tension: 0.3,
                    spanGaps: false,
                    order: 4
                },
                {
                    label: 'Forecast',
                    data: forecast,
                    borderColor: CHART_COLORS.blue,
                    borderWidth: 2.5,
                    borderDash: [6, 4],
                    backgroundColor: 'transparent',
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: CHART_COLORS.blue,
                    spanGaps: false,
                    order: 2
                },
                {
                    label: 'Actual',
                    data: actual,
                    borderColor: CHART_COLORS.emerald,
                    backgroundColor: CHART_COLORS.emeraldFaded,
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: CHART_COLORS.emerald,
                    spanGaps: false,
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    filter: function(item) {
                        return item.dataset.label !== 'Upper Bound' && item.dataset.label !== 'Lower Bound';
                    },
                    callbacks: {
                        label: function(ctx) {
                            if (ctx.parsed.y === null) return null;
                            return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 12, font: { size: 10 } }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(v) { return v + '%'; }
                    }
                }
            }
        }
    });
}

/* ==========================================================================
   initEbitdaChart  --  Daily EBITDA contribution (grouped bar chart)
   canvasId     : string
   labels       : string[]
   currentData  : number[]
   optimalData  : number[]   (optional -- if omitted, single dataset shown)
   ========================================================================== */
function initEbitdaChart(canvasId, labels, currentData, optimalData) {
    destroyIfExists(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    var datasets = [
        {
            label: 'Current EBITDA',
            data: currentData,
            backgroundColor: 'rgba(96, 165, 250, 0.7)',    // blue-400
            borderColor: 'rgb(96, 165, 250)',
            borderWidth: 1,
            borderRadius: 4,
            barPercentage: 0.8,
            categoryPercentage: 0.7
        }
    ];

    if (optimalData) {
        datasets.push({
            label: 'Optimal EBITDA',
            data: optimalData,
            backgroundColor: 'rgba(52, 211, 153, 0.7)',    // emerald-400
            borderColor: 'rgb(52, 211, 153)',
            borderWidth: 1,
            borderRadius: 4,
            barPercentage: 0.8,
            categoryPercentage: 0.7
        });
    }

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString();
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 10 }, maxRotation: 45 }
                },
                y: {
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(v) { return '$' + (v / 1000).toFixed(0) + 'k'; }
                    }
                }
            }
        }
    });
}

/* ==========================================================================
   initScatterChart  --  Rate vs Occupancy tradeoff
   canvasId : string
   data     : Array<{ current: {x, y}, optimal: {x, y} }>
   ========================================================================== */
function initScatterChart(canvasId, data) {
    destroyIfExists(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    var currentPoints = data.map(function(d) { return d.current; });
    var optimalPoints = data.map(function(d) { return d.optimal; });

    new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: 'Current',
                    data: currentPoints,
                    backgroundColor: 'rgba(96, 165, 250, 0.6)',
                    borderColor: 'rgb(96, 165, 250)',
                    borderWidth: 1.5,
                    pointRadius: 6,
                    pointHoverRadius: 8
                },
                {
                    label: 'Optimal',
                    data: optimalPoints,
                    backgroundColor: 'rgba(52, 211, 153, 0.6)',
                    borderColor: 'rgb(52, 211, 153)',
                    borderWidth: 1.5,
                    pointRadius: 6,
                    pointHoverRadius: 8,
                    pointStyle: 'rectRounded'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.dataset.label +
                                   ': Rate $' + ctx.parsed.x.toFixed(0) +
                                   ', Occ ' + ctx.parsed.y.toFixed(1) + '%';
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Average Daily Rate ($)', font: { size: 11, weight: '500' } },
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(v) { return '$' + v; }
                    }
                },
                y: {
                    title: { display: true, text: 'Occupancy %', font: { size: 11, weight: '500' } },
                    min: 40,
                    max: 100,
                    grid: { color: 'rgba(0,0,0,0.04)' },
                    ticks: {
                        font: { size: 10 },
                        callback: function(v) { return v + '%'; }
                    }
                }
            }
        }
    });
}
