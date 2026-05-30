// === COMPANY PROFILE JS ===
// company.html?symbol=TLV

var SIMBOL = null;
var CD = null;        // company_data.json
var PORTFOLIO = null; // bvb_portfolio.json (for current price)
var priceChart = null;
var revChart = null;
var niChart = null;

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
    var capStr = cap >= 1e9 ? (cap/1e9).toFixed(1) + 'B RON' :
                 cap >= 1e6 ? (cap/1e6).toFixed(0) + 'M RON' :
                 fmt(cap, 0) + ' RON';
    items.push({label: 'Market Cap', val: capStr});
  }

  var pe = metrics.trailingPE || metrics.forwardPE;
  if (pe) items.push({label: 'P/E (TTM)', val: pe.toFixed(1)});

  if (metrics.forwardPE) items.push({label: 'Forward P/E', val: metrics.forwardPE.toFixed(1)});

  if (metrics.dividendYield) {
    items.push({label: 'Dividend Yield', val: (metrics.dividendYield * 100).toFixed(2) + '%'});
  }

  if (metrics.dividendRate) {
    items.push({label: 'Dividend anual', val: metrics.dividendRate.toFixed(4) + ' RON'});
  }

  if (metrics.profitMargins) {
    items.push({label: 'Marja profit', val: (metrics.profitMargins * 100).toFixed(1) + '%'});
  }

  var html = '';
  for (var i = 0; i < items.length; i++) {
    html += '<div class="mm-item"><div class="mm-label">' + items[i].label +
            '</div><div class="mm-val">' + items[i].val + '</div></div>';
  }
  el.innerHTML = html || '<div style="color:var(--dim);font-size:.82rem;padding:8px">Nicio metrica disponibila</div>';
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
    case '1d':  cutoff = new Date(now.getTime() - 1 * 24 * 60 * 60 * 1000); break;
    default: cutoff = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
  }

  return prices.filter(function(p) { return new Date(p.date) >= cutoff; });
}

function renderPriceChart() {
  var comp = CD && CD.companies ? CD.companies[SIMBOL] : null;
  if (!comp || !comp.price_history || !comp.price_history.length) {
    document.getElementById('ch-no-chart').style.display = '';
    return;
  }

  document.getElementById('ch-no-chart').style.display = 'none';
  var period = document.getElementById('ch-period').value;
  var prices = filterPriceHistory(comp.price_history, period);

  if (!prices.length) {
    document.getElementById('ch-no-chart').style.display = '';
    return;
  }

  var labels = prices.map(function(p) {
    var d = new Date(p.date);
    return d.toLocaleDateString('ro-RO', {month:'short', day:'numeric'});
  });
  var data = prices.map(function(p) { return p.close; });
  var color = data[data.length - 1] >= data[0] ? '#22c55e' : '#ef4444';

  if (priceChart) priceChart.destroy();
  var ctx = document.getElementById('ch-price-chart').getContext('2d');
  priceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Pret inchidere (RON)',
        data: data,
        borderColor: color,
        backgroundColor: color + '20',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.1,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: '#8b8fa3', font: { size: 9 }, maxTicksLimit: 10 },
          grid: { color: 'rgba(42,45,58,0.3)' }
        },
        y: {
          ticks: { color: '#8b8fa3', font: { size: 10 }, callback: function(v) { return v.toFixed(2); } },
          grid: { color: 'rgba(42,45,58,0.3)' }
        }
      }
    }
  });
}

// === FINANCIAL RESULTS ===
function renderFinancials(comp) {
  if (!comp.quarterly || !comp.quarterly.length) {
    document.getElementById('ch-fin-section').style.display = 'none';
    return;
  }

  document.getElementById('ch-fin-section').style.display = '';

  var qs = comp.quarterly.slice(0, 12).reverse();

  var labels = qs.map(function(q) {
    var d = new Date(q.date);
    return d.toLocaleDateString('ro-RO', {month:'short', year:'2-digit'});
  });

  var revenues = qs.map(function(q) { return q.revenue || 0; });
  var netIncome = qs.map(function(q) { return q.netIncome || 0; });

  // Revenue chart
  if (revChart) revChart.destroy();
  var ctxR = document.getElementById('ch-rev').getContext('2d');
  revChart = new Chart(ctxR, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Venituri (RON)',
        data: revenues,
        backgroundColor: '#6366f1'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8b8fa3', font: { size: 8 } }, grid: { display: false } },
        y: { ticks: { color: '#8b8fa3', font: { size: 9 }, callback: function(v) { return v >= 1e6 ? (v/1e6).toFixed(0) + 'M' : v; } }, grid: { color: 'rgba(42,45,58,0.3)' } }
      }
    }
  });

  // Net income chart
  if (niChart) niChart.destroy();
  var ctxN = document.getElementById('ch-ni').getContext('2d');
  var niColors = netIncome.map(function(v) { return v >= 0 ? '#22c55e' : '#ef4444'; });
  niChart = new Chart(ctxN, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Profit net (RON)',
        data: netIncome,
        backgroundColor: niColors
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8b8fa3', font: { size: 8 } }, grid: { display: false } },
        y: { ticks: { color: '#8b8fa3', font: { size: 9 }, callback: function(v) { return v >= 1e6 ? (v/1e6).toFixed(0) + 'M' : v; } }, grid: { color: 'rgba(42,45,58,0.3)' } }
      }
    }
  });
}

// === MAIN ===
function init() {
  SIMBOL = parseSymbol();

  if (!SIMBOL) {
    showError('Niciun simbol specificat. Adauga ?symbol=TLV in URL.');
    return;
  }

  showLoading(true);

  // Load company_data.json AND bvb_portfolio.json in parallel
  var loaded = 0;
  var total = 2;

  function checkDone() {
    loaded++;
    if (loaded < total) return;
    render();
  }

  fetch('company_data.json?_=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      CD = data;
      checkDone();
    })
    .catch(function() {
      CD = { companies: {} };
      checkDone();
    });

  fetch('bvb_portfolio.json?_=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      PORTFOLIO = data;
      checkDone();
    })
    .catch(function() {
      PORTFOLIO = null;
      checkDone();
    });
}

function render() {
  var comp = CD.companies[SIMBOL];

  if (!comp) {
    showError('Simbolul "' + SIMBOL + '" nu a fost gasit in baza de date.');
    return;
  }

  showContent();

  // Header
  document.getElementById('ch-sym').textContent = SIMBOL;
  document.getElementById('ch-name').textContent = comp.nume || '';

  // Tags
  var tags = [];
  if (comp.metrics && comp.metrics.sector) tags.push('<span class="tag">' + comp.metrics.sector + '</span>');
  if (comp.metrics && comp.metrics.industry) tags.push('<span class="tag g">' + comp.metrics.industry + '</span>');
  document.getElementById('ch-tags').innerHTML = tags.join('');

  // Price from portfolio data
  renderPrice();

  // Summary
  if (comp.metrics && comp.metrics.longBusinessSummary) {
    document.getElementById('ch-summary').textContent = comp.metrics.longBusinessSummary;
  } else {
    document.getElementById('ch-summary').style.display = 'none';
  }

  // Metrics
  renderMetrics(comp.metrics || {});

  // Price chart
  renderPriceChart();

  // Financial results
  renderFinancials(comp);

  // News link
  var q = encodeURIComponent((comp.nume || SIMBOL) + ' BVB');
  document.getElementById('ch-news').href = 'https://news.google.com/search?q=' + q + '&hl=ro';
}

function renderPrice() {
  if (!PORTFOLIO || !PORTFOLIO.holdings) {
    document.getElementById('ch-price').textContent = '-';
    document.getElementById('ch-change').textContent = '-';
    return;
  }

  var h = null;
  for (var i = 0; i < PORTFOLIO.holdings.length; i++) {
    if (PORTFOLIO.holdings[i].simbol === SIMBOL) {
      h = PORTFOLIO.holdings[i];
      break;
    }
  }

  if (h) {
    document.getElementById('ch-price').textContent = fmt(h.pret_actual_RON, 4);
    var cls = h.variatie_pret_pct >= 0 ? 'pos' : 'neg';
    document.getElementById('ch-change').innerHTML = '<span class="' + cls + '">' + fmtPct(h.variatie_pret_pct) + '</span>';
  } else {
    // Not in portfolio — try company_data for last close
    var comp = CD.companies[SIMBOL];
    if (comp && comp.price_history && comp.price_history.length) {
      var last = comp.price_history[comp.price_history.length - 1];
      document.getElementById('ch-price').textContent = fmt(last.close, 4);
      document.getElementById('ch-change').textContent = '';
    } else {
      document.getElementById('ch-price').textContent = '-';
      document.getElementById('ch-change').textContent = '';
    }
  }
}

// BOOT
init();
