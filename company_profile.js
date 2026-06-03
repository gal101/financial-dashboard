// === COMPANY PROFILE JS ===
// company.html?symbol=TLV

var SIMBOL = null;
var CD = null;
var PORTFOLIO = null;
var priceChart = null;
var annChart = null;
var qChart = null;
var finMode = 'profit';  // 'profit' or 'venituri'
Chart.register(Chart.Filler);
var chartType = 'line';

function parseSymbol() {
  var m = location.search.match(/[?&]symbol=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function showLoading(show) {
  document.getElementById('ld').style.display = show ? '' : 'none';
}

function showError(msg) {
  document.getElementById('ld').style.display = 'none';
  document.getElementById('ch-body').style.display = 'none';
  document.getElementById('ch-error').style.display = '';
  document.getElementById('ch-error-msg').textContent = msg || '';
}

function showContent() {
  document.getElementById('ld').style.display = 'none';
  document.getElementById('ch-body').style.display = '';
  document.getElementById('ch-error').style.display = 'none';
}

function fmt(n, dec) {
  if (n === null || n === undefined || isNaN(n)) return '-';
  dec = (dec === undefined) ? 2 : dec;
  return n.toLocaleString('ro-RO', {minimumFractionDigits: dec, maximumFractionDigits: dec});
}

function fmtPct(n) {
  if (n === null || n === undefined || isNaN(n)) return '-';
  var sign = n >= 0 ? '+' : '';
  return sign + n.toFixed(2) + '%';
}

// === METRICS ===
function renderMetrics(metrics) {
  var el = document.getElementById('ch-metrics');
  var items = [];

  if (metrics.marketCap) {
    var cap = metrics.marketCap;
    var capStr = cap >= 1e9 ? (cap/1e9).toFixed(1) + 'B' : cap >= 1e6 ? (cap/1e6).toFixed(0) + 'M' : fmt(cap,0);
    items.push({l: 'Market Cap', v: capStr + ' RON'});
  }
  var pe = metrics.trailingPE;
  if (pe) items.push({l: 'P/E (TTM)', v: pe.toFixed(2)});
  if (metrics.forwardPE) items.push({l: 'Forward P/E', v: metrics.forwardPE.toFixed(2)});
  if (metrics.ttm_net_income && metrics.sharesOutstanding) {
    var eps = metrics.ttm_net_income / metrics.sharesOutstanding;
    items.push({l: 'EPS (TTM)', v: eps.toFixed(4) + ' RON'});
  }
  if (metrics.priceToBook && metrics.priceToBook > 0) items.push({l: 'Price/Book', v: metrics.priceToBook.toFixed(2)});
  if (metrics.dividendYield && metrics.dividendYield > 0) {
    var dv = metrics.dividendYield.toFixed(2) + '%';
    if (metrics.dividend && metrics.dividend > 0) {
      dv += '<br><span style="font-size:.65rem;color:var(--dim)">' + metrics.dividend.toFixed(4) + ' RON/act</span>';
    }
    // Total dividend for user's position
    if (PORTFOLIO && PORTFOLIO.holdings) {
      for (var hi = 0; hi < PORTFOLIO.holdings.length; hi++) {
        if (PORTFOLIO.holdings[hi].simbol === SIMBOL) {
          var shares = PORTFOLIO.holdings[hi].actiuni;
          if (shares && metrics.dividend && metrics.dividend > 0) {
            dv += '<br><span style="font-size:.65rem;color:var(--dim)">Al tau: ' + (metrics.dividend * shares).toFixed(2) + ' RON</span>';
          }
          break;
        }
      }
    }
    items.push({l: 'Dividend', v: dv});
  }
  if (metrics.profitMargins) items.push({l: 'Marja profit', v: (metrics.profitMargins * 100).toFixed(2) + '%'});

  var html = '';
  for (var i = 0; i < items.length; i++) {
    html += '<div class="mm-item"><div class="mm-label">' + items[i].l + '</div><div class="mm-val">' + items[i].v + '</div></div>';
  }
  el.innerHTML = html || '<span style="color:var(--dim);font-size:.7rem">Nicio metrica</span>';
}

// === HELPERS ===
function niceScale(data, padPct) {
  if (!data || !data.length) return { min: 0, max: 0 };
  padPct = padPct || 0.10;
  var mn = Math.min.apply(null, data);
  var mx = Math.max.apply(null, data);
  var range = mx - mn || Math.abs(mx) || 1;
  var pad = range * padPct;
  var adjMin = mn >= 0 ? Math.max(0, mn - pad) : mn - pad;
  var adjMax = mx + pad;
  return { min: adjMin, max: adjMax };
}

function fmtAxis(v) {
  if (v === 0) return '0';
  var abs = Math.abs(v);
  var sign = v < 0 ? '-' : '';
  if (abs >= 1e6) return sign + (abs / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
  return sign + abs.toFixed(0);
}

// === PRICE CHART ===
function filterPriceHistory(prices, period) {
  if (!prices || !prices.length) return [];
  var now = new Date();
  var cutoff;
  switch (period) {
    case '5y':  cutoff = new Date(now.getFullYear() - 5, now.getMonth(), now.getDate()); break;
    case '3y':  cutoff = new Date(now.getFullYear() - 3, now.getMonth(), now.getDate()); break;
    case '1y':  cutoff = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate()); break;
    case '6mo': cutoff = new Date(now.getTime() - 180 * 24 * 60 * 60 * 1000); break;
    case '3mo': cutoff = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000); break;
    case '1mo': cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break;
    case '1wk': cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break;
    default: cutoff = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
  }
  return prices.filter(function(p) { return new Date(p.date) >= cutoff; });
}


var currentPeriod = '1y';

function renderPriceChart() {
  var comp = CD && CD.companies ? CD.companies[SIMBOL] : null;
  if (!comp || !comp.price_history || !comp.price_history.length) {
    document.getElementById('ch-no-chart').style.display = '';
    return;
  }
  document.getElementById('ch-no-chart').style.display = 'none';
  var prices = filterPriceHistory(comp.price_history, currentPeriod);
  if (!prices.length) { document.getElementById('ch-no-chart').style.display = ''; return; }

  var longPeriod = (currentPeriod === '5y' || currentPeriod === '3y');
  var labels = prices.map(function(p) {
    var d = new Date(p.date);
    if (longPeriod) return d.toLocaleDateString('ro-RO', {month:'short', year:'2-digit'});
    return d.toLocaleDateString('ro-RO', {month:'short', day:'numeric'});
  });
  var data = prices.map(function(p) { return p.close; });
  var color = data[data.length - 1] >= data[0] ? '#22c55e' : '#ef4444';

  // Price change badge
  var firstPrice = data[0], lastPrice = data[data.length - 1];
  var pctChange = firstPrice ? ((lastPrice - firstPrice) / firstPrice * 100) : 0;
  var pctStr = (pctChange >= 0 ? '+' : '') + pctChange.toFixed(1) + '%';
  var badge = document.getElementById('ch-pct-badge');
  badge.textContent = pctStr;
  badge.style.display = '';
  badge.style.background = pctChange >= 0 ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)';
  badge.style.color = pctChange >= 0 ? '#4ade80' : '#f87171';

  if (priceChart) priceChart.destroy();
  var ctx = document.getElementById('ch-price-chart').getContext('2d');

  var datasets = [];
  
  // Volume Dataset (Always present as background overlay)
  var volumeData = prices.map(function(p) { return p.volume || 0; });
  var maxVol = Math.max.apply(null, volumeData);
  if (maxVol <= 0) maxVol = 1;

  datasets.push({
    type: 'bar',
    label: 'Volum',
    data: volumeData,
    backgroundColor: 'rgba(59, 130, 246, 0.12)', // light blue overlay
    borderColor: 'transparent',
    yAxisID: 'yVolume',
    order: 3
  });

  if (chartType === 'line') {
    datasets.push({
      type: 'line',
      label: 'Preț Închidere',
      data: data,
      borderColor: color,
      backgroundColor: color + '20',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.1,
      fill: true,
      yAxisID: 'y',
      order: 1
    });
  } else if (chartType === 'range') {
    // Dataset 0: Low Boundary (Invisible)
    datasets.push({
      type: 'line',
      label: 'Minim',
      data: prices.map(function(p) { return p.low !== null && p.low !== undefined ? p.low : p.close; }),
      borderColor: 'transparent',
      pointRadius: 0,
      fill: false,
      yAxisID: 'y',
      order: 2
    });
    // Dataset 1: High Boundary (Filled to Low)
    datasets.push({
      type: 'line',
      label: 'Maxim',
      data: prices.map(function(p) { return p.high !== null && p.high !== undefined ? p.high : p.close; }),
      borderColor: 'transparent',
      pointRadius: 0,
      fill: '-1', // references previous dataset (index 0 - Low)
      backgroundColor: 'rgba(139, 143, 163, 0.15)', // Shaded range band
      yAxisID: 'y',
      order: 1
    });
    // Dataset 2: Close Price Line
    datasets.push({
      type: 'line',
      label: 'Preț Închidere',
      data: data,
      borderColor: color,
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.1,
      yAxisID: 'y',
      order: 0
    });
  }

  priceChart = new Chart(ctx, {
    type: 'line',
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
          mode: 'index',
          intersect: false,
          callbacks: {
            label: function(ctx) {
              return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(4) + ' RON';
            }
          }
        }
      },
      scales: {
        x: { ticks: { color: '#8b8fa3', font: { size: 8 }, maxTicksLimit: 8 }, grid: { color: 'rgba(42,45,58,0.3)' } },
        y: { type: 'linear', position: 'left', ticks: { color: '#8b8fa3', font: { size: 9 }, callback: function(v) { return v.toFixed(2); } }, grid: { color: 'rgba(42,45,58,0.3)' } },
        yVolume: {
          type: 'linear',
          position: 'right',
          display: false,
          grid: { display: false },
          max: maxVol * 5
        }
      }
    }
  });
}

// === FINANCIAL CHARTS (annual + quarterly, toggle profit/venituri) ===
function renderFinancialCharts(comp) {
  var hasQuarterly = comp.quarterly && comp.quarterly.length;
  var hasAnnual = comp.annual && comp.annual.length;

  if (!hasQuarterly && !hasAnnual) {
    document.getElementById('ch-fin-empty').style.display = '';
    return;
  }
  document.getElementById('ch-fin-empty').style.display = 'none';

  var field = finMode === 'profit' ? 'Net Income' : 'Total Revenue';

  // === ANNUAL CHART ===
  if (hasAnnual) {
    var ann = comp.annual.slice(0, 5).sort(function(a,b) { return new Date(a.date) - new Date(b.date); });
    var annLabels = ann.map(function(a) { return String(new Date(a.date).getFullYear()); });
    var annData = ann.map(function(a) { return (a.items && a.items[field]) || 0; });

    // BVC
    var hasBvc = comp.bvc && comp.bvc.revenue != null;
    var isProfit = finMode === 'profit';
    var bvcVal = null;
    if (hasBvc) {
      bvcVal = isProfit ? comp.bvc.net_income : comp.bvc.revenue;
      annLabels.push(String(comp.bvc.year));
      annData.push(bvcVal);
    }

    var annColors = annData.map(function(_, i) {
      if (hasBvc && i === annData.length - 1) return '#e879f9';
      if (isProfit) return annData[i] >= 0 ? '#22c55e' : '#ef4444';
      return '#6366f1';
    });

    var annScale = niceScale(annData);

    if (annChart) annChart.destroy();
    var ctxA = document.getElementById('ch-ann-chart').getContext('2d');
    annChart = new Chart(ctxA, {
      type: 'bar',
      data: { labels: annLabels, datasets: [{ data: annData, backgroundColor: annColors, borderRadius: 3 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { type: 'category', ticks: { color: '#8b8fa3', font: { size: 9 } }, grid: { display: false } },
          y: { beginAtZero: false, min: annScale.min, max: annScale.max, ticks: { color: '#8b8fa3', font: { size: 8 }, callback: fmtAxis }, grid: { color: 'rgba(42,45,58,0.3)' } }
        }
      }
    });
  }

  // === QUARTERLY CHART ===
  if (hasQuarterly) {
    var qs = comp.quarterly.slice(-12);
    var qLabels = qs.map(function(q) {
      var d = new Date(q.date);
      var qnum = Math.ceil((d.getMonth() + 1) / 3);
      var yy = String(d.getFullYear()).slice(2);
      return 'Q' + qnum + ' ' + yy;
    });
    var qData = qs.map(function(q) { return (q.items && q.items[field]) || 0; });
    var qColors = isProfit ? qData.map(function(v) { return v >= 0 ? '#22c55e' : '#ef4444'; }) : '#6366f1';
    var qScale = niceScale(qData);

    if (qChart) qChart.destroy();
    var ctxQ = document.getElementById('ch-q-chart').getContext('2d');
    qChart = new Chart(ctxQ, {
      type: 'bar',
      data: { labels: qLabels, datasets: [{ data: qData, backgroundColor: qColors, borderRadius: 2 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8b8fa3', font: { size: 7 } }, grid: { display: false } },
          y: { beginAtZero: false, min: qScale.min, max: qScale.max, ticks: { color: '#8b8fa3', font: { size: 8 }, callback: fmtAxis }, grid: { color: 'rgba(42,45,58,0.3)' } }
        }
      }
    });
  }
}

// === CALENDAR ===
function renderCalendar(comp) {
  if (!comp.calendar || !comp.calendar.length) {
    document.getElementById('ch-cal-section').style.display = 'none';
    return;
  }
  document.getElementById('ch-cal-section').style.display = '';

  var now = new Date();
  var events = comp.calendar.sort(function(a,b) { return new Date(a.date) - new Date(b.date); });
  var html = '<div style="position:relative;display:flex;justify-content:space-evenly;align-items:flex-start;gap:8px;padding:8px 4px 2px;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin">';
  html += '<div style="position:absolute;top:18px;left:24px;right:24px;height:1px;background:var(--border)"></div>';

  for (var i = 0; i < events.length; i++) {
    var ev = events[i];
    var d = new Date(ev.date);
    var day = d.toLocaleDateString('ro-RO', {day:'numeric'});
    var month = d.toLocaleDateString('ro-RO', {month:'short'});
    var isPast = d < now;
    var dotColor = isPast ? 'var(--dim)' : '#818cf8';

    html += '<div style="flex:0 0 auto;display:flex;flex-direction:column;align-items:center;position:relative;z-index:1;min-width:85px">';
    html += '<div style="width:9px;height:9px;border-radius:50%;background:' + dotColor + ';border:2px solid var(--bg);margin-bottom:4px"></div>';
    html += '<div style="text-align:center;opacity:' + (isPast ? '0.5' : '1') + '">';
    html += '<div style="font-size:.68rem;font-weight:600;color:' + dotColor + '">' + day + ' ' + month + '</div>';
    html += '<div style="font-size:.65rem;color:' + (isPast ? 'var(--dim)' : 'var(--text)') + ';line-height:1.2;max-width:90px">' + ev.event + '</div>';
    html += '</div></div>';
  }
  html += '</div>';
  document.getElementById('ch-cal-list').innerHTML = html;
}

// === MAIN ===
function init() {
  SIMBOL = parseSymbol();
  if (!SIMBOL) { showError('Niciun simbol specificat. Adauga ?symbol=TLV in URL.'); return; }
  showLoading(true);

  var loaded = 0;
  function checkDone() { loaded++; if (loaded >= 2) render(); }

  fetch('company_data.json?_=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(d) { CD = d; checkDone(); })
    .catch(function() { CD = { companies: {} }; checkDone(); });

  fetch('bvb_portfolio.json?_=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(d) { PORTFOLIO = d; checkDone(); })
    .catch(function() { PORTFOLIO = null; checkDone(); });
}

function render() {
  var comp = CD.companies[SIMBOL];
  if (!comp) { showError('Simbolul "' + SIMBOL + '" nu a fost gasit in baza de date.'); return; }
  showContent();

  // Header info
  document.getElementById('ch-sym').textContent = SIMBOL;
  document.getElementById('ch-name').textContent = comp.nume || '';

  var tags = [];
  if (comp.metrics && comp.metrics.sector) tags.push('<span class="tag">' + comp.metrics.sector + '</span>');
  if (comp.metrics && comp.metrics.industry) tags.push('<span class="tag g">' + comp.metrics.industry + '</span>');
  document.getElementById('ch-tags').innerHTML = tags.join('');

  renderPrice(comp);
  renderMetrics(comp.metrics || {});

  // No summary text — it just repeats the company name

  var q = encodeURIComponent((comp.nume || SIMBOL) + ' BVB');
  document.getElementById('ch-news').href = 'https://news.google.com/search?q=' + q + '&hl=ro';

  renderPriceChart();
  renderFinancialCharts(comp);
  renderCalendar(comp);
}

function renderPrice(comp) {
  if (!PORTFOLIO || !PORTFOLIO.holdings) { document.getElementById('ch-price').textContent = '-'; document.getElementById('ch-change').textContent = ''; return; }
  var h = null;
  for (var i = 0; i < PORTFOLIO.holdings.length; i++) {
    if (PORTFOLIO.holdings[i].simbol === SIMBOL) { h = PORTFOLIO.holdings[i]; break; }
  }
  if (h) {
    document.getElementById('ch-price').textContent = fmt(h.pret_actual_RON, 4) + ' RON';
    var cls = h.variatie_pret_pct >= 0 ? 'pos' : 'neg';
    document.getElementById('ch-change').innerHTML = '<span class="' + cls + '">' + fmtPct(h.variatie_pret_pct) + '</span>';
  } else if (comp && comp.price_history && comp.price_history.length) {
    var last = comp.price_history[comp.price_history.length - 1];
    document.getElementById('ch-price').textContent = fmt(last.close, 4) + ' RON';
    document.getElementById('ch-change').textContent = '';
  } else {
    document.getElementById('ch-price').textContent = '-';
    document.getElementById('ch-change').textContent = '';
  }
}


// === EVENT LISTENERS ===
document.addEventListener('DOMContentLoaded', function() {
  // Period buttons
  document.getElementById('ch-period-btns').addEventListener('click', function(e) {
    var btn = e.target.closest('button');
    if (!btn) return;
    var btns = document.getElementById('ch-period-btns').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('on');
    btn.classList.add('on');
    currentPeriod = btn.dataset.p;
    renderPriceChart();
  });

  // Chart type toggle buttons
  document.getElementById('ch-type-btns').addEventListener('click', function(e) {
    var btn = e.target.closest('button');
    if (!btn) return;
    var btns = document.getElementById('ch-type-btns').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('on');
    btn.classList.add('on');
    chartType = btn.dataset.t;
    renderPriceChart();
  });

  // Profit/Venituri toggle
  document.getElementById('ch-fin-toggle').addEventListener('click', function(e) {
    var btn = e.target.closest('button');
    if (!btn) return;
    var btns = document.getElementById('ch-fin-toggle').querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('on');
    btn.classList.add('on');
    finMode = btn.dataset.mode;
    var comp = CD && CD.companies ? CD.companies[SIMBOL] : null;
    if (comp) renderFinancialCharts(comp);
  });
  var highlightTimer = null;

  // Live price streaming via SSE
  var es = new EventSource('/api/monitor/events');
  es.addEventListener('price', function(e) {
    try {
      var tick = JSON.parse(e.data);
      if (tick.sim === SIMBOL && tick.pret) {
        var comp = CD && CD.companies ? CD.companies[SIMBOL] : null;
        var oldPrice = comp ? (comp.pret_actual_RON || comp.last_price) : null;
        var newPrice = tick.pret;
        var prEl = document.getElementById('ch-price');
        if (prEl) {
          prEl.textContent = fmt(newPrice, 4) + ' RON';
          if (oldPrice !== null && oldPrice !== newPrice) {
            if (highlightTimer) {
              clearTimeout(highlightTimer);
              highlightTimer = null;
            }
            prEl.classList.remove('flash-green', 'flash-red');
            void prEl.offsetWidth; // trigger reflow
            var flashClass = newPrice > oldPrice ? 'flash-green' : 'flash-red';
            prEl.classList.add(flashClass);
            highlightTimer = setTimeout(function() {
              prEl.classList.remove(flashClass);
              highlightTimer = null;
            }, 3000);
          }
        }
        var change_pct = tick.ref ? ((tick.pret - tick.ref) / tick.ref * 100) : 0;
        var cls = change_pct >= 0 ? 'pos' : 'neg';
        var chEl = document.getElementById('ch-change');
        if (chEl) {
          chEl.innerHTML = '<span class="' + cls + '">' + fmtPct(change_pct / 100) + '</span>';
        }
        if (comp) {
          comp.pret_actual_RON = newPrice;
          if (comp.metrics) {
            var m = comp.metrics;
            if (m.sharesOutstanding) {
              m.marketCap = newPrice * m.sharesOutstanding;
              var eps = m.ttm_net_income / m.sharesOutstanding;
              if (eps > 0) m.trailingPE = newPrice / eps;
            }
            if (m.bookValuePerShare) m.priceToBook = newPrice / m.bookValuePerShare;
            else if (m.bookValue && m.sharesOutstanding) {
              var bvps = m.bookValue / m.sharesOutstanding;
              if (bvps > 0) m.priceToBook = newPrice / bvps;
            }
            if (m.dividend && m.dividend > 0) m.dividendYield = (m.dividend / newPrice) * 100;
            renderMetrics(m);
          }
        }
      }
    } catch(err) {
      console.error('Error parsing SSE price tick:', err);
    }
  });
});

init();
