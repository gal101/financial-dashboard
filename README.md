# BVB Portfolio Dashboard

A self-hosted, real-time portfolio tracker for the Bucharest Stock Exchange (BVB). Fetches live prices from Yahoo Finance, displays key metrics, and provides detailed company profiles with financial charts — all served as a static web dashboard.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Live price updates** — fetches current prices from Yahoo Finance for all BVB tickers (`.RO` suffix)
- **Portfolio KPIs** — total invested, current value, P/L, overall return percentage at a glance
- **Holdings table** — sortable table with price, change %, allocation weight, and unrealized P/L per position
- **Sector allocation pie chart** — breakdown by economic sector (Banking, IT, Energy, Agriculture, etc.)
- **Benchmark vs BET Index** — compare your portfolio performance against the BET index over custom periods
- **Company Profile modal** (click any symbol) — deep-dive view with:
  - Key financial metrics (Market Cap, P/E, P/B, ROE, ROA, Dividend Yield, Beta, D/E, etc.)
  - Price history chart with period selector (1D → 5Y)
  - Historical P/E chart
  - Quarterly revenue & net income bar charts (last 12 quarters)
  - Annual revenue bar chart (last 3–5 years)
  - Daily trading volume chart
- **"Refresh prices" button** — fetches live prices from the browser (no server reload needed)
- **Cron-automated updates** — Python script runs on schedule to refresh JSON data files
- **Dark theme UI** — clean, modern dashboard styled for readability

## Architecture

```
yfinance API (Yahoo Finance)
        │
        ▼
portfolio_updater.py  ──→  bvb_portfolio.json  (private, gitignored)
company_fetcher.py    ──→  company_data.json   (public financial data)
        │                        │
        └────────┬───────────────┘
                 ▼
         dashboard.html  (static, served via nginx)
                 │
                 ▼
            Browser (Chart.js for charts)
```

- **`portfolio_updater.py`** — fetches current prices from Yahoo Finance, updates `bvb_portfolio.json`
- **`company_fetcher.py`** — fetches quarterly/annual financials, key metrics, and price history; saves to `company_data.json`
- **`dashboard.html`** — fully self-contained static dashboard; loads JSON data at boot and can fetch live prices on demand
- **nginx** — serves the static files as a web app (Docker or bare-metal)

## Tech Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Data fetching | Python 3, `yfinance`                |
| Data format   | JSON files                          |
| Frontend      | Vanilla HTML/CSS/JS, Chart.js 4     |
| Server        | nginx (Docker or bare-metal)        |
| Automation    | Hermes Agent cron jobs              |

## Quick Start

### Prerequisites

- Python 3.11+ with `yfinance` (`pip install yfinance`)
- nginx (or any static file server)
- Git

### 1. Clone the repo

```bash
git clone https://github.com/gal101/financial-dashboard.git
cd financial-dashboard
```

### 2. Set up your portfolio

```bash
# Copy the example file and edit it with your real holdings
cp bvb_portfolio.example.json bvb_portfolio.json
nano bvb_portfolio.json  # add your tickers, share counts, and purchase prices
```

> **Important:** `bvb_portfolio.json` is gitignored — it contains your real holdings and will **never** be committed to the repo.

### 3. Install Python dependencies

```bash
pip install yfinance
```

### 4. Fetch initial data

```bash
python3 portfolio_updater.py      # fetches live prices
python3 company_fetcher.py        # fetches company financials
```

### 5. Serve the dashboard

```bash
# Quick local test (Python built-in server)
python3 -m http.server 8080

# Or with nginx/Docker (recommended for production)
docker run -d --name dashboard \
  -v $(pwd):/usr/share/nginx/html:ro \
  -p 80:80 nginx:alpine
```

Open `http://localhost:8080` (or your server's IP) in a browser.

### 6. Automate price updates (optional)

Set up a cron job to run the updater periodically:

```bash
# Example: every 30 minutes on weekdays
*/30 * * * 1-5 cd /financial-dashboard && python3 portfolio_updater.py
```

Or use Hermes Agent's built-in cron:

```
hermes cron create \
  --name "bvb-price-update" \
  --schedule "30m" \
  --prompt "Run portfolio_updater.py and company_fetcher.py in /financial-dashboard"
```

## File Overview

| File                         | Purpose                                      | Committed? |
|------------------------------|----------------------------------------------|------------|
| `dashboard.html`             | Main web dashboard (HTML/CSS/JS + Chart.js)  | Yes        |
| `portfolio_updater.py`       | Fetches live prices from Yahoo Finance       | Yes        |
| `company_fetcher.py`         | Fetches company financials & metrics         | Yes        |
| `bvb_portfolio.json`         | Your actual holdings (prices, P/L, shares)   | **No**     |
| `bvb_portfolio.example.json` | Anonymized template for new setups           | Yes        |
| `company_data.json`          | Public company data (metrics, financials)    | Yes        |
| `FEATURES.md`                | Detailed feature roadmap & planning doc      | Yes        |
| `.gitignore`                 | Git ignore rules                             | Yes        |

## Supported Tickers

The dashboard supports BVB-listed companies via Yahoo Finance's `.RO` suffix:

- `TLV.RO` — Banca Transilvania
- `SNP.RO` — OMV Petrom
- `SNG.RO` — Romgaz
- `FP.RO` — Fondul Proprietatea
- `H2O.RO` — Sphera Franchise Group
- `BENTO.RO` — Bento
- `SAFE.RO` — Safetech Innovations
- ... and any other BVB ticker available on Yahoo Finance

Structured products (e.g., `EBTLV*` tickers issued by Erste Bank) are not available on Yahoo Finance and are skipped during price fetching.

> Tip: always check `https://finance.yahoo.com/quote/<TICKER>.RO` to confirm a ticker exists before adding it.

## Security

- **`bvb_portfolio.json` is NEVER committed.** It contains your real share counts, purchase prices, and P/L. It is listed in `.gitignore`.
- The `bvb_portfolio.example.json` file contains an anonymized structure — safe to share publicly.
- Always run `git status` before committing to verify you're not accidentally staging your private data.

## Roadmap

See [FEATURES.md](FEATURES.md) for the full feature plan. Highlights planned:

- [ ] Budget overlay + forward P/E estimation (requires BVB scraping)
- [ ] Dividend tracker with ex-date calendar
- [ ] Watchlist for monitored (non-held) tickers
- [ ] Financial calendar (earnings dates, AGM, dividends)
- [ ] Transaction history import (CSV → JSON)
- [ ] Price alerts via Telegram
- [ ] IR (Investor Relations) links auto-discovery

## License

MIT — see [LICENSE](LICENSE) file (if present) or use freely.
