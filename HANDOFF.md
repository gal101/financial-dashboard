# BVB Financial Dashboard — Handoff Document
## Session: 2026-05-31 (Session 2) | Hermes + DeepSeek V4 Pro

### What We Built / Fixed

Major redesign and data accuracy overhaul of the BVB company profile page (company.html + company_profile.js).

**Layout:**
- Two-column responsive layout: left = metrics cards, right = price chart + calendar
- Toggle button (Profit ↔ Venituri) switches both annual and quarterly charts
- Calendar timeline: horizontal scrollable row with dots + connecting line, no vertical scrollbar
- Price chart with period buttons (1S 1L 3L 6L 1A 3A 5A), badge showing +/- X% change
- Container stretches full viewport (max-width: none, min-height: 100vh, centered)
- Right column uses `justify-content: flex-end` so chart stays at bottom when left column is taller

**Data Accuracy — BENTO fixed:**
| Metric | Before (Yahoo) | After (calculated) | Source |
|--------|:---:|:---:|--------|
| trailingPE | 7.57 | **14.35** | TTM Q2'25–Q1'26 / 14M shares |
| forwardPE | 25.79 | **11.21** | BVC 2026: 11.09M NI |
| dividendYield | 3.29% | **0%** | Last dividend paid in 2023 |
| profitMargins | 15.2% | **16.7%** | TTM calc: 8.66M / 51.84M |
| EPS | N/A | **0.6188** | TTM / 14M shares |
| price_history | 248 entries (1Y) | **1044 entries** | 5Y from yfinance (Mar 2022–May 2026) |

**P/E calculation methodology (CRITICAL for future agents):**
- P/E = marketCap / TTM_net_income (last 4 completed quarters)
- Shares outstanding: 14,000,000 (user confirmed)
- Q4 2025 was derived (FY2025 - Q1-Q3), Q1 2026 from official Q1 2026 report
- TTM for BENTO: Q2'25 + Q3'25 + Q4'25 + Q1'26 = 8,663,414

**BVC (Budget) for BENTO — found and integrated:**
- Source: https://www.bento.ro/adunari-generale-ale-actionarilor/ → `7.-BVC-punctul-5-de-pe-ordinea-de-zi-AGOA.pdf`
- BVC 2026: revenue 88.1M, net income 11.09M (+73% vs 2025)
- BVC bars appear in annual chart as fuchsia (#e879f9), single dataset approach
- Pattern for other companies: look for AGOA/AGEA pages, search for "BVC" PDF among meeting docs
- BVC typically published Jan-Apr for current year

### Architecture (Current State)

```
/financial-dashboard/
├── company.html              # Company Profile (redesigned)
├── company_profile.js        # JS for company.html (chart rendering, metrics, calendar)
├── dashboard.html            # Portfolio + Watchlist
├── style.css                 # Shared CSS (dark theme)
├── portfolio_updater.py      # Fetch prices (yfinance)
├── company_fetcher.py        # Fetch company data — uses period="5y"
├── metrics_calculator.py     # Calculates trailingPE, forwardPE, EPS, profit margin
├── bvc_parser.py             # Parses BVC from Excel/PDF
├── db.py                     # SQLite data access layer (schema, queries, export, backup)
├── json_sanitizer.py         # Prevents NaN in JSON from yfinance
├── company_data.json         # Derived JSON export (gitignored, regenerable)
├── bvb_dashboard.db          # SQLite source of truth (gitignored)
├── bvb_portfolio.json        # Portfolio holdings (gitignored)
├── watchlist.json            # Watchlist symbols
├── server/                   # Python HTTP API (:8089, accesibil prin nginx :8080)
│   ├── server.py
│   ├── handlers/refresh.py, watchlist.py
│   ├── scraper/trigger.py    # Webhook to Hermes
│   └── shared/config.py
├── scrape_results/           # Scraped data (gitignored)
├── db_backups/               # SQLite backups (gitignored)
├── PRD.md                    # Product requirements document
├── CONTEXT.md                # Glossary + metric formulas
├── HANDOFF.md                # This file
├── FEATURES.md               # Backlog
└── .gitignore
```

### Known Issues / TODO

1. **shares_outstanding missing** — Only BENTO (14M) and SMTL (8.14M) have shares_outstanding. Needed for EPS + market_cap calculation for TLV, SNP, PE, SAFE, DN, DIGI, H2O. Source: BVB.ro page curl.

2. **priceToBook only for DN** — Only DN has calculated price_to_book (2.24). Need official book value from balance sheets for others.

3. **BVB.ro blocked** from some IPs — may need alternate scraping approach.

4. **Scraping scripts not commited** — Lots of experimental scrapers in scrape_results/ (`parse_safe*.py`, `extract_*.py`, etc.). Should be cleaned up or committed to git.

5. **MSTL removed from DB** — Was a typo for SMTL. Cleared 2026-06-02.

### BVC Status (✅ Completed)

BVC extracted and rendered in company profile for all 7 companies:
- BENTO (AGOA 2026), TLV (BVB.ro), SNP (omvpetrom.com), H2O (hidroelectrica.ro), DN (dn-agrar.eu), SAFE (safetech.ro), SMTL (simtel.ro)

BVC data lives in SQLite (`bvc` table) and is exported to each company's `bvc` field in JSON. The company_profile.js renders it as a fuchsia (#e879f9) bar in the annual chart.

### Suggested Skills for Next Session

- `hermes-agent` — webhook and gateway management
- `browserless` — Playwright scraping on :3000 (if browser is available)
- `self-hosted-dashboard` — dashboard server management
- `subagent-driven-development` — if implementing multiple company scrapes in parallel
- `writing-plans` — if planning new features

### Key Patterns Learned

- **BVC location:** Company site → `/adunari-generale-ale-actionarilor/` → PDF with "BVC" in filename. Works for BENTO, likely same for other Romanian companies (required by BVB regulation).
- **P/E formula:** `marketCap / TTM_net_income` (last 4 quarters). NOT annual fiscal year. Tradeville uses this same formula.
- **Dividend:** Check if company actually paid dividend recently. BENTO last paid in 2023 (for FY2022). Yahoo's dividendYield is often stale/wrong.
- **Calendar:** BVB.ro `/info/Raportari/` might have calendar data, but site blocks non-browser requests. Playwright needed.
- **Chart layout fix:** `justify-content: flex-end` on right column prevents empty gap when left column is taller.

### Reference Files

- PRD: `/financial-dashboard/PRD.md`
- Context glossary: `/financial-dashboard/CONTEXT.md`
- BENTO BVC PDF (downloaded): `https://www.bento.ro/wp-content/uploads/2026/03/7.-BVC-punctul-5-de-pe-ordinea-de-zi-AGOA.pdf`
- Hermes config: `/opt/data/config.yaml`
- Dashboard server: `/financial-dashboard/server/` (nginx :8080 → Python :8089)
