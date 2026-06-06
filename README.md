# BVB Portfolio Dashboard

A self-hosted, real-time portfolio tracker for the Bucharest Stock Exchange (BVB). Fetches live prices via the Tradeville API WebSocket gateway, calculates financial metrics from official company data, and displays everything in a dark-themed web dashboard with detailed company profiles.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.13+-blue)

## Features

- **Live price updates** — fetches current prices via Tradeville API WebSocket push for all BVB tickers
- **Portfolio KPIs** — total invested, current value, P/L, overall return percentage at a glance
- **Holdings table** — sortable table with price, change %, allocation weight, and unrealized P/L per position
- **Sector allocation pie chart** — breakdown by economic sector (Banking, IT, Energy, Agriculture, etc.)
- **Dividend tracker** — dividend yield, dividend rate, estimated annual dividend income from Tradeville data
- **Watchlist** — monitor symbols you don't hold (DIGI, H2O, SMTL) with live prices
- **Company Profile page** (click any symbol) — deep-dive view with:
  - Key financial metrics (Market Cap, trailing P/E, forward P/E, P/B, EPS, Dividend Yield, etc.)
  - Price history chart with period selector (1S → 5A) and chart type toggle (Line / Min-Max Range)
  - Volume overlay on price chart
  - Toggle between Profit and Revenue charts
  - Quarterly revenue & net income bar charts (last 12 quarters)
  - Annual revenue bar chart with BVC (budget) overlay
  - Calendar timeline with corporate events
- **Offline fallback** — all endpoints serve cached SQLite data when Tradeville WebSocket is disconnected
- **Rate-limited gateway** — single WebSocket connection with 0.6s cooldown between sends (max 20 req/10s)
- **Automated portfolio sync** — pulls holdings directly from Tradeville account (symbols, quantities, buy prices)
- **Transaction history** — syncs account activity (buys, sells, dividends) from Tradeville
- **Dark theme UI** — clean, modern dashboard styled for readability

## Architecture
```
┌────────────────────────────────────────────────────────────────────┐
│ Cron jobs Hermes (Task Pings to /api/monitor/task-ping)            │
│  07:00 UTC L-V  →  portfolio_updater.py (Tradeville API)            │
│  15:00 UTC L-V  →  portfolio_updater.py (Tradeville API)            │
│  15:30 UTC L-V  →  company_fetcher.py (Incremental OHLCV)           │
│                    │                                                 │
│                    ▼                                                 │
│               db.upsert_prices() → price_history (SQLite)            │
└────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────┐
│ TradevilleStreamer (WebSocket daemon thread)                        │
│   wss://api.tradeville.ro:443 (apitv)                               │
│   ┌──────────┐  ┌───────────┐  ┌────────────┐                      │
│   │TX (0.6s) │  │RX (match) │  │Push Workers│                      │
│   │out_queue │  │pending_req│  │push_queue  │                      │
│   └──────────┘  └───────────┘  └─────┬──────┘                      │
│        │              │               │                             │
│        ▼              ▼               ▼                             │
│   ┌─────────────────────────────────────────┐                      │
│   │ HTTP Proxy: POST /api/tradeville/request│                      │
│   └────────────────────┬────────────────────┘                      │
│                        │ Broadcast Live Ticks                      │
│                        ▼                                           │
│                 sse_manager (SSE)                                  │
└────────────────────────┬───────────────────────────────────────────┘
                         │
                         ▼ (Live SSE Stream: /api/monitor/events)
┌────────────────────────────────────────────────────────────────────┐
│ Unified ThreadingHTTPServer (Port 8089)                             │
│   - Serves Frontend: dashboard.html, company.html, monitor.html    │
│   - Serves REST API: /company, /watchlist, /transactions, /logs    │
│   - Streams SSE Events (logs, price ticks, task states, ws_status) │
│   - Handles Control Endpoints (/api/monitor/*)                     │
│                    │                                                 │
│                    ▼                                                 │
│              bvb_dashboard.db (SQLite, WAL mode)                     │
└────────────────────────────────────────────────────────────────────┘
```

### Data flow principles

- **SQLite is the single source of truth** (`bvb_dashboard.db`). `company_data.json` is a read-only export for the frontend.
- **Green zone** (`price_history`): written by `company_fetcher.py` and real-time push workers.
- **Red zone** (`companies`, `quarterly`, `annual`, `bvc`, `calendar`, `calculated_metrics`): written only via curated scraping, never by automated scripts.
- **Market cap** is calculated dynamically as `shares_outstanding × last close`.
- **JSON sanitizer** prevents NaN/Inf from poisoning the frontend.

## Tech Stack

| Layer         | Technology                                  |
|---------------|---------------------------------------------|
| Database      | SQLite 3 (WAL mode)                         |
| Data fetching | Tradeville API (WebSocket + HTTP proxy)     |
| Server        | Python `ThreadingHTTPServer` (port 8089)     |
| Frontend      | Vanilla HTML/CSS/JS, Chart.js 4             |
| Live Stream   | Server-Sent Events (SSE)                    |
| Automation    | Hermes Agent cron jobs + webhooks           |
## Quick Start

### Prerequisites

- Python 3.11+
- Tradeville API credentials (`.env` file)
- `websocket-client`, `python-dotenv`, `requests`, `pytz`

### 1. Clone the repo

```bash
git clone https://github.com/gal101/financial-dashboard.git
cd financial-dashboard
```

### 2. Set up credentials

```bash
# Copy the example and add your Tradeville credentials
python setup_credentials.py
# Or edit .env directly:
# TRADEVILLE_USER=your_user_code
# TRADEVILLE_PASSWORD=your_password
# TRADEVILLE_DEMO=true|false
```

> Demo credentials available: `!DemoAPITDV` / `DemoAPITDV` with `TRADEVILLE_DEMO=true`

### 3. Install dependencies

```bash
pip install -r back-end/requirements.txt
```

### 4. Start the server
```bash
python back-end/server.py
```
Open `http://localhost:8089/dashboard.html`.

### 5. Fetch initial data (optional — runs automatically on startup)

```bash
python back-end/portfolio_updater.py      # fetches live prices → SQLite + JSON
python back-end/company_fetcher.py        # fetches OHLCV history + metadata → price_history
```

## File Overview

| File                         | Purpose                                           | Committed? |
|------------------------------|---------------------------------------------------|------------|
| `front-end/dashboard.html`    | Main web dashboard (HTML/CSS/JS + Chart.js)       | Yes        |
| `front-end/company.html`      | Company Profile page (click on symbol)            | Yes        |
| `front-end/monitor.html`      | Server Monitor UI (live logs, tasks status)       | Yes        |
| `front-end/company_profile.js`| Chart rendering, metrics display, calendar        | Yes        |
| `front-end/style.css`         | Shared dark theme CSS                             | Yes        |
| `back-end/portfolio_updater.py`| Fetches live prices + syncs portfolio from Tradeville | Yes   |
| `back-end/company_fetcher.py` | Fetches 5Y OHLCV history + company metadata       | Yes        |
| `back-end/metrics_calculator.py`| Calculates trailingPE, forwardPE, EPS from raw  | Yes        |
| `back-end/db.py`             | SQLite data access layer (schema, queries, export)| Yes        |
| `back-end/json_sanitizer.py`  | safe_json_dumps() — prevents NaN in JSON          | Yes        |
| `back-end/server.py`          | Python HTTP API (:8089) + Tradeville proxy        | Yes        |
| `back-end/shared/tradeville_streamer.py` | WebSocket gateway to Tradeville API   | Yes        |
| `back-end/shared/tradeville_client.py`  | HTTP client helper for scripts          | Yes        |
| `back-end/shared/activity_sync.py`     | Transaction history sync                | Yes        |
| `back-end/setup_credentials.py` | Interactive credential setup CLI                | Yes        |
| `tests/test_tradeville.py`    | Integration test for the proxy + gateway          | Yes        |
| `data/bvb_dashboard.db`       | SQLite database (curated financial data)          | Yes        |
| `data/company_data.json`      | Derived JSON export (regenerated from DB)         | Yes        |
| `data/bvb_portfolio.json`     | Your actual holdings (prices, P/L, shares)        | **No**     |
| `data/bvb_portfolio.example.json` | Anonymized template for new setups              | Yes        |
| `docs/NEW-PRD.md`             | Product requirements document                     | Yes        |
| `docs/FEATURES.md`            | Detailed feature roadmap & planning doc           | Yes        |
| `docs/CONTEXT.md`             | Glossary of financial terms and formulas          | Yes        |
| `README.md`                   | This file                                         | Yes        |

## Supported Tickers

The dashboard supports BVB-listed companies via the Tradeville API:

- `TLV` — Banca Transilvania
- `SNP` — OMV Petrom
- `BENTO` — 2B Intelligent Soft
- `SAFE` — Safetech Innovations
- `PE` — Premier Energy
- `DN` — DN Agrar Group
- `H2O` — Hidroelectrica
- `DIGI` — Digi Communications
- `SMTL` — Simtel Team
- ... and any other BVB ticker available on Tradeville

Structured products (e.g., `EBTLVTL19` turbo certificates) are also supported.

## Security

- **`.env` is NEVER committed.** It contains your Tradeville credentials. It is listed in `.gitignore`.
- **`bvb_portfolio.json` is NEVER committed.** It contains your real share counts, purchase prices, and P/L.
- The `bvb_portfolio.example.json` file contains an anonymized structure — safe to share publicly.

## Roadmap

See [FEATURES.md](FEATURES.md) for the full feature plan.

### Implemented
- Portfolio KPIs + holdings table
- Company Profile page (metrics, price chart, quarterly/annual results, BVC overlay, calendar)
- Sector allocation pie chart
- Dividend tracker (yield, rate, estimated annual income)
- Watchlist with add/delete and live prices
- Dual chart view (Line / Min-Max Range) with volume overlay
- Automated portfolio sync from Tradeville account
- Transaction history sync from Tradeville
- Cron-automated updates (3 Hermes jobs)
- SQLite persistence with green/red zone separation
- Offline fallback — all data served from cache when WebSocket is down
- Rate-limited gateway (0.6s cooldown, max 20 req/10s)

### Planned
- Dividend calendar (ex-date tracking)
- Price alerts via Telegram
- IR (Investor Relations) links auto-discovery
- Benchmark vs BET Index in portfolio view

## License

MIT — see [LICENSE](LICENSE) file (if present) or use freely.
