# BVB Portfolio Dashboard

A self-hosted, real-time portfolio tracker for the Bucharest Stock Exchange (BVB). Fetches live prices from Yahoo Finance, calculates proper financial metrics from official company data (not Yahoo's often-wrong values), and displays everything in a dark-themed web dashboard with detailed company profiles.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.13+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Live price updates** — fetches current prices from Yahoo Finance for all BVB tickers (`.RO` suffix)
- **Portfolio KPIs** — total invested, current value, P/L, overall return percentage at a glance
- **Holdings table** — sortable table with price, change %, allocation weight, and unrealized P/L per position
- **Sector allocation pie chart** — breakdown by economic sector (Banking, IT, Energy, Agriculture, etc.)
- **Dividend tracker** — dividend yield, dividend rate, estimated annual dividend income
- **Benchmark vs BET Index** — compare your portfolio performance against the BET index over custom periods
- **Watchlist** — monitor symbols you don't hold (DIGI, H2O, SMTL) with live prices
- **Company Profile page** (click any symbol) — deep-dive view with:
  - Key financial metrics (Market Cap, trailing P/E, forward P/E, P/B, ROE, ROA, Dividend Yield, Beta, D/E, etc.)
  - Price history chart with period selector (1S → 5A)
  - Toggle between Profit and Revenue charts
  - Quarterly revenue & net income bar charts (last 12 quarters)
  - Annual revenue bar chart with BVC (budget) overlay in fuchsia
  - Calendar timeline with corporate events
- **"Refresh prices" button** — fetches live prices from the browser (no server reload needed)
- **Cron-automated updates** — 3 Hermes cron jobs update prices daily (07:00, 15:00, 15:30 UTC, L-V)
- **Dark theme UI** — clean, modern dashboard styled for readability

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│ Cron jobs Hermes (3 joburi, livrare Telegram)                      │
│  07:00 UTC L-V  →  portfolio_updater.py (yfinance)                 │
│  15:00 UTC L-V  →  portfolio_updater.py (yfinance)                 │
│  15:30 UTC L-V  →  company_fetcher.py (yfinance 5Y prices)         │
│                    │                                                │
│                    ▼                                                │
│               db.upsert_prices() → price_history (SQLite)           │
│               db.export_to_json() → company_data.json               │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│ Browser (fetch /refresh, /company?symbol=X)                        │
│                    │                                                │
│                    ▼                                                │
│ nginx :8080 (static files: dashboard.html, company.html)           │
│                    │                                                │
│                    ▼                                                │
│ Server Python :8089 (backend API, proxied by nginx)                │
│   GET  /company?symbol=X  →  db.get_company()  →  JSON             │
│   GET  /companies         →  db.list_companies() →  JSON           │
│   POST /refresh           →  portfolio_updater.py                   │
│   POST /watchlist         →  add/remove symbols                     │
│   POST /scrape-callback   →  scraping pipeline callback             │
│                    │                                                │
│                    ▼                                                │
│              bvb_dashboard.db (SQLite, WAL mode)                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│ Scraping pipeline (manual trigger via Hermes webhook)               │
│   Search company site → download Excel/PDF → parse financial data   │
│   → upsert into SQLite (quarterly, annual, bvc, calculated_metrics) │
│   → export_to_json() → company_data.json                            │
│                                                                     │
│   BVC source: company.ro /adunari-generale-ale-actionarilor/ PDF    │
│   BVB.ro: curl static HTML for PER, PBV, EPS, DIVY, shares          │
└────────────────────────────────────────────────────────────────────┘
```

### Data flow principles

- **SQLite is the single source of truth** (`bvb_dashboard.db`). `company_data.json` is a read-only export for the frontend.
- **Green zone** (`price_history`): only `company_fetcher.py` writes here (yfinance prices).
- **Red zone** (`companies`, `quarterly`, `annual`, `bvc`, `calendar`, `calculated_metrics`): written only via curated scraping, never by automated scripts.
- **Market cap** is calculated dynamically as `shares_outstanding × last close` — never stored.
- **JSON sanitizer** prevents NaN/Inf from yfinance poisoning the frontend.

## Tech Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Database      | SQLite 3 (WAL mode)                 |
| Data fetching | Python 3, `yfinance`                |
| Backend API   | Python `http.server` (port 8089)    |
| Frontend      | Vanilla HTML/CSS/JS, Chart.js 4     |
| Static server | nginx (port 8080, proxy to :8089)   |
| Automation    | Hermes Agent cron jobs + webhooks   |
| Scraping      | Playwright via browserless (CDP)    |

## Quick Start

### Prerequisites

- Python 3.11+ with `yfinance`, `openpyxl`, `pymupdf`
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
pip install yfinance openpyxl pymupdf
```

### 4. Initialize database

```bash
python3 db.py   # creates bvb_dashboard.db with all tables
```

### 5. Fetch initial data

```bash
python3 portfolio_updater.py      # fetches live prices → SQLite + JSON
python3 company_fetcher.py        # fetches company financials → price_history
python3 json_sanitizer.py         # sanitize JSON for the browser
```

### 6. Serve the dashboard

```bash
# Start the Python API server
python3 server/server.py &

# Or with nginx (recommended for production)
# Configure nginx to serve /financial-dashboard as static files
# and proxy /company, /refresh, /watchlist to localhost:8089
```

Open `http://localhost:8080` (or your server's IP) in a browser.

### 7. Automate price updates (optional)

Set up Hermes cron jobs:

```bash
hermes cron create \
  --name "bvb-price-morning" \
  --schedule "0 7 * * 1-5" \
  --prompt "Run python3 /financial-dashboard/portfolio_updater.py"
```

## File Overview

| File                         | Purpose                                           | Committed? |
|------------------------------|---------------------------------------------------|------------|
| `dashboard.html`             | Main web dashboard (HTML/CSS/JS + Chart.js)       | Yes        |
| `company.html`               | Company Profile page (click on symbol)            | Yes        |
| `company_profile.js`         | Chart rendering, metrics display, calendar        | Yes        |
| `style.css`                  | Shared dark theme CSS                             | Yes        |
| `portfolio_updater.py`       | Fetches live prices from Yahoo Finance            | Yes        |
| `company_fetcher.py`         | Fetches 5Y price history → price_history table    | Yes        |
| `metrics_calculator.py`      | Calculates trailingPE, forwardPE, EPS from raw    | Yes        |
| `bvc_parser.py`              | Parses BVC (budget) from Excel/PDF files          | Yes        |
| `db.py`                      | SQLite data access layer (schema, queries, export)| Yes        |
| `json_sanitizer.py`          | safe_json_dumps() — prevents NaN in JSON          | Yes        |
| `migrate_to_sqlite.py`       | One-shot: migrate JSON → SQLite                   | Yes        |
| `server/server.py`           | Python HTTP API (:8089)                           | Yes        |
| `server/handlers/`           | HTTP handlers (refresh, watchlist)                | Yes        |
| `server/scraper/trigger.py`  | Webhook callback handler for scraping pipeline    | Yes        |
| `bvb_dashboard.db`           | SQLite database (curated financial data)     | Yes        |
| `company_data.json`          | Derived JSON export (regenerated from DB)    | Yes        |
| `bvb_portfolio.json`         | Your actual holdings (prices, P/L, shares)        | **No**     |
| `bvb_portfolio.example.json` | Anonymized template for new setups                | Yes        |
| `PRD.md`                     | Product requirements document                     | Yes        |
| `FEATURES.md`                | Detailed feature roadmap & planning doc           | Yes        |
| `CONTEXT.md`                 | Glossary of financial terms and formulas          | Yes        |
| `HANDOFF.md`                 | Session handoff notes                             | Yes        |
| `README.md`                  | This file                                         | Yes        |

## Supported Tickers

The dashboard supports BVB-listed companies via Yahoo Finance's `.RO` suffix:

- `TLV.RO` — Banca Transilvania
- `SNP.RO` — OMV Petrom
- `BENTO.RO` — 2B Intelligent Soft
- `SAFE.RO` — Safetech Innovations
- `PE.RO` — Premier Energy
- `DN.RO` — DN Agrar Group
- `H2O.RO` — Hidroelectrica
- `DIGI.RO` — Digi Communications
- `SMTL.RO` — Simtel Team
- ... and any other BVB ticker available on Yahoo Finance

Structured products (e.g., `EBTLV*` tickers issued by Erste Bank) are not available on Yahoo Finance and are skipped during price fetching.

> Tip: always check `https://finance.yahoo.com/quote/<TICKER>.RO` to confirm a ticker exists before adding it.

## Security

- **`bvb_portfolio.json` is NEVER committed.** It contains your real share counts, purchase prices, and P/L. It is listed in `.gitignore`.
- The `bvb_portfolio.example.json` file contains an anonymized structure — safe to share publicly.
- Always run `git status` before committing to verify you're not accidentally staging your private data.

## Roadmap

See [FEATURES.md](FEATURES.md) for the full feature plan (including items planned for future iterations).

### ✅ Implemented
- Portfolio KPIs + holdings table
- Company Profile page (metrics, price chart, quarterly/annual results, BVC overlay, calendar)
- Sector allocation pie chart
- Dividend tracker (yield, rate, estimated annual income)
- Watchlist with add/delete and live prices
- Price refresh button
- Cron-automated updates (3 Hermes jobs)
- SQLite persistence with green/red zone separation
- BVC (budget) extraction from official company PDFs — 7 companies done
- Calculated trailingPE, forwardPE, EPS from official data (not Yahoo)

### 🔜 Planned
- Dividend calendar (ex-date tracking)
- Transaction history import (CSV)
- Price alerts via Telegram
- IR (Investor Relations) links auto-discovery
- Benchmark vs BET Index in portfolio view

## License

MIT — see [LICENSE](LICENSE) file (if present) or use freely.
