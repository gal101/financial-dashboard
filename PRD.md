# PRD — BVB Portfolio Dashboard v1

> Product Requirements Document — MVP + SQLite Migration
> Bazat pe FEATURES.md, rafinat prin grill-with-docs
> 30 mai 2026, actualizat 1 iunie 2026 (migrare SQLite + upsert fix)

## Scop

Dashboard personal de investitii BVB (Bursa de Valori Bucuresti). Utilizator: Andrei (single user). Self-hosted pe server personal, accesibil local/Tailscale.

**Principiu fundamental:** Nu ne bazam pe Yahoo Finance pentru metrici calculate (P/E, P/B, etc.) — Yahoo intoarce frecvent valori gresite pentru actiunile BVB. Extragem datele brute din surse oficiale (site-uri companii, BVB.ro) si calculam noi metricile.

**Principiu de persistenta (nou — 1 iunie 2026):** SQLite este sursa unica de adevar. `company_data.json` este un artefact derivat (export read-only) pentru frontend, nu sursa primara. Scripturile automate nu scriu niciodata direct in JSON — toate scrierile trec prin `db.py`.

---

## Status implementare (2 iunie 2026)

### ✅ Finalizat

1. **Pas 1: Webhook Hermes** ✅
2. **Pas 2: Server Python + Refresh button** ✅
3. **Pas 3: Watchlist persistent** ✅
4. **Pas 4: Scraping pipeline v1 (Yahoo fallback)** ✅
5. **Migrare SQLite** ✅ — Baza de date `bvb_dashboard.db` cu 7 tabele
6. **Cron jobs Hermes** ✅ — 3 joburi programate, livrare pe Telegram home channel
7. **Export automat JSON** ✅ — `export_to_json()` genereaza `company_data.json` din SQLite
8. **Backup automat** ✅ — `db.backup()` salveaza in `db_backups/`
9. **JSON sanitizer** ✅ — `json_sanitizer.py` previne NaN in JSON (yfinance bug)
10. **Upsert cu tranzactii** ✅ — `upsert_prices` foloseste `INSERT ... ON CONFLICT DO UPDATE` cu `BEGIN IMMEDIATE`
11. **Pas 5: Scraping pipeline v2 (partial)** ✅ — Date oficiale extrase pentru BENTO, TLV, SNP, H2O, DN, SAFE, SMTL. BVC in SQLite. trailingPE/forwardPE calculate pentru 9/9 companii.
12. **Pas 6: BVC in graficele anuale** ✅ — BVC apare ca bara fuchsia in chartul anual pentru toate cele 7 companii cu date.
13. **Calcul metrici proprii** ✅ — trailingPE, forwardPE, EPS din date brute (nu Yahoo)
14. **Calendar financiar** ✅ — Evenimente corporate din scrape_results

### 🔜 Planificat (post-MVP)

1. **shares_outstanding pentru toate companiile** — necesar pentru EPS si market_cap
2. **priceToBook din bilant oficial** — momentan doar DN are valoare
3. **Dividend tracker calendar** — ex-date tracking
4. **Istoric tranzactii CSV** — import din Tradeville
5. **Alerte de pret** — Telegram notifications
6. **IR links auto-discovery** — linkuri Investor Relations

---

## Arhitectura (actualizat 1 iunie 2026)

### Schema SQLite

```sql
-- ZONA ROSIE: read-only pentru scripturi, scris doar prin scraping/curation
companies (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    shares_outstanding INTEGER,
    market_cap REAL           -- NOT stored; calculated as shares_outstanding × last close
);

quarterly (symbol, date, revenue, net_income, source);       -- PK(symbol, date)
annual    (symbol, date, revenue, net_income, source);       -- PK(symbol, date)
bvc       (symbol, year, revenue, net_income, source);       -- PK(symbol, year)
calendar  (symbol, date, event);                             -- PK(symbol, date)
calculated_metrics (symbol, trailing_pe, forward_pe, eps,
                    profit_margin, price_to_book, dividend_yield, updated_at);

-- ZONA VERDE: singura tabela in care company_fetcher.py poate scrie
price_history (symbol, date, close);                         -- PK(symbol, date)
```

### Zone de acces

| Zona | Tabele | Cine scrie | Cine citeste |
|------|--------|------------|--------------|
| 🟢 Verde | `price_history` | `company_fetcher.py` (yfinance) | Toate |
| 🔴 Rosie | `companies`, `quarterly`, `annual`, `bvc`, `calendar`, `calculated_metrics` | Curatare manuala / scraping v2 | Toate |

**Regula:** `company_fetcher.py` NU are voie sa scrie in nicio tabela din zona rosie. `market_cap` nu e stocat — se calculeaza dinamic din `shares_outstanding × ultimul close`.

### Operatiuni critice

- **`upsert_prices()`**: `INSERT ... ON CONFLICT(symbol, date) DO UPDATE` + `BEGIN IMMEDIATE` + `rollback` pe eroare. Fara DELETE. Atomic.
- **`upsert_calendar()`**: Inca foloseste DELETE + INSERT (necesita acelasi fix ca price_history)
- **`upsert_quarterly/annual/bvc/metrics`**: Folosesc `INSERT OR REPLACE` — corect pentru ca suprascriu seturi complete de date

### Fișiere

```
/financial-dashboard/
├── bvb_dashboard.db              # Sursa unica de adevar (SQLite, WAL mode)
├── db_backups/                   # Backup-uri timestamped
├── db.py                         # Data access layer (schema, queries, export, backup)
├── company_data.json             # Artefact derivat (export read-only din SQLite)
├── json_sanitizer.py             # safe_json_dumps() — previne NaN in JSON
│
├── dashboard.html                # UI Portfolio + Watchlist
├── company.html                  # UI Company Profile (?symbol=X)
├── company_profile.js            # JS pentru company.html (grafice, metrici)
├── style.css                     # CSS comun
│
├── company_fetcher.py            # Cron: fetch preturi yfinance → price_history
├── portfolio_updater.py          # Cron: actualizare preturi portofoliu
├── metrics_calculator.py         # Post-MVP: calculeaza P/E, P/B, EPS din date brute
├── bvc_parser.py                 # Post-MVP: extrage BVC din Excel/PDF
├── migrate_to_sqlite.py          # One-shot: migrare JSON → SQLite (istoric)
│
├── server/                       # Server Python HTTP
│   ├── server.py                 # API: /refresh, /watchlist, /company, /scrape-callback, /health
│   ├── handlers/
│   │   ├── refresh.py            # POST /refresh — ruleaza portfolio_updater.py
│   │   └── watchlist.py          # GET/POST/DELETE /watchlist
│   ├── scraper/
│   │   └── trigger.py            # POST /scrape-callback (post-MVP)
│   └── shared/
│       └── config.py
│
├── bvb_portfolio.json            # Detineri reale ❌ gitignorat
├── bvb_portfolio.example.json    # Structura anonimizata
├── watchlist.json                # Simboluri urmarite ✅ committable
├── pending_scrapes.json          # Task-uri scraping (post-MVP) ❌ gitignorat
├── scrape_results/               # Rezultate scraping (post-MVP) ❌ gitignorat
│
├── PRD.md                        # Acest document
├── FEATURES.md                   # Backlog complet
├── CONTEXT.md                    # Glosar
├── README.md                     # Docs
└── .gitignore
```

### Flux de date (actualizat 1 iunie 2026)

```
┌─────────────────────────────────────────────────────────────────┐
│ Cron jobs Hermes (3 joburi, livrare Telegram home channel)       │
│                                                                  │
│ 07:00 UTC L-V  →  portfolio_updater.py                          │
│ 15:00 UTC L-V  →  portfolio_updater.py                          │
│ 15:30 UTC L-V  →  company_fetcher.py                            │
│                      │                                           │
│                      ▼                                           │
│              yfinance API (5Y daily prices)                      │
│                      │                                           │
│                      ▼                                           │
│         db.upsert_prices() → price_history (zona verde)         │
│         db.export_to_json() → company_data.json                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Browser (fetch la SVR/refresh, SVR/company?symbol=X)            │
│                      │                                           │
│                      ▼                                           │
| nginx :8080 (static files: dashboard.html, company.html)        │
│                      │                                           │
│                      ▼                                           │
│ Server Python :8089 (backend API, proxied by nginx)             │
│   GET  /company?symbol=X  →  db.get_company()  →  JSON          │
│   GET  /companies         →  db.list_companies() →  JSON        │
│   POST /refresh           →  portfolio_updater.py               │
│   POST /scrape-callback   →  scraping v2 (post-MVP)             │
│                      │                                           │
│                      ▼                                           │
│              bvb_dashboard.db (SQLite, WAL mode)                 │
└─────────────────────────────────────────────────────────────────┘
```

### Decizii de arhitectura

1. **SQLite peste JSON** — Integritate referentiala (FK), tranzactii atomice, WAL mode pentru citiri concurente. JSON-ul e derivat, nu sursa.
2. **Zona verde/rosie** — Separare clara intre ce poate scrie un script automat (doar price_history) si ce necesita curatare manuala. Previne stergerea accidentala a datelor financiare.
3. **market_cap nu e stocat** — Se calculeaza din `shares_outstanding × ultimul close`. Evita inconsistentele intre market_cap stocat si pretul curent.
4. **yfinance period="5y"** — Yahoo returneaza ultimii ~5 ani. Fereastra e controlata de Yahoo, nu de noi. Upsert-ul adauga zile noi fara sa stearga istoricul vechi.
5. **Tranzactii explicite** — `BEGIN IMMEDIATE` + `commit()`/`rollback()`. Daca fetch-ul pica, datele raman intacte.
6. **json_sanitizer.py** — yfinance poate intoarce `NaN` in preturi (bug cunoscut). `safe_json_dumps()` inlocuieste `NaN`/`Inf` cu `null` inainte de serializare. Fara asta, JSON-ul e invalid si browserul crapa.
7. **Cron jobs → Telegram** — Toate cele 3 joburi livrau initial `local` (doar salvare). Acum toate livreaza pe Telegram home channel pentru vizibilitate imediata.

---

## Cron Jobs

| Job | Program | Script | Zona | Livrare |
|-----|---------|--------|------|---------|
| BVB portfolio morning | 07:00 UTC, L-V | `portfolio_updater.py` | price_history | Telegram |
| BVB portfolio evening | 15:00 UTC, L-V | `portfolio_updater.py` | price_history | Telegram |
| Company financial data | 15:30 UTC, L-V | `company_fetcher.py` | price_history | Telegram |

Toate cele 3 joburi ruleaza cu `workdir=/financial-dashboard` si `enabled_toolsets=["terminal"]`.

---

## Pas 5: Scraping pipeline v2 — Date oficiale companii (post-MVP)

**Obiectiv:** In loc sa ne bazam pe metricile calculate de Yahoo (deseori gresite pentru BVB), extragem datele financiare direct din sursa oficiala si calculam noi indicatorii.

**Flux scraping v2:**
```
Adaugare simbol in watchlist
  │
  ▼
Google Search: "BENTO investor relations" sau "2B Intelligent Soft relatii investitori"
  │
  ▼
Identificare site oficial → pagina Investitori / Relatii Investitori
  │
  ▼
Cautare rapoarte: Excel (.xlsx) preferat, PDF ca fallback
  ├── Rezultate financiare trimestriale/anuale
  ├── Buget de Venituri si Cheltuieli (BVC) — pentru anul curent
  └── Indicatori financiari (P/E, EPS, book value per share)
  │
  ▼
Download + parsare Excel (openpyxl) sau PDF (pymupdf/pdfplumber)
  │
  ▼
Extragere date brute → scriere in SQLite (zona rosie: quarterly, annual, bvc)
  │
  ▼
Calculare metrici proprii (metrics_calculator.py):
  trailingPE = marketCap / TTM_net_income
  forwardPE  = marketCap / forward_net_income (din BVC)
  priceToBook = marketCap / book_value
  EPS = TTM_net_income / shares_outstanding
  │
  ▼
Scriere in calculated_metrics + export_to_json()
```

**Target-uri per companie:**

| Categorie | Sursa | Format preferat |
|-----------|-------|-----------------|
| Rezultate financiare | Site companie → Investors | .xlsx |
| BVC (buget) | Site companie → Investors → Buget | .xlsx / .pdf |
| Numar actiuni | BVB.ro (pagina simbol) | HTML static (merge curl) |
| Calendar financiar | BVB.ro → Calendar | HTML |
| Indicatori BVB (PER, PBV, EPS, DIVY) | BVB.ro → pagina simbol | HTML static |

**De ce nu Yahoo pentru metrici calculate:**
- Yahoo calculeaza trailingPE din ultimul an fiscal complet, nu TTM
- forwardPE pentru BVB e deseori trailingPE deghizat (nu exista estimari de analisti)
- profitMargins, revenueGrowth, earningsGrowth — inconsistent pentru companii mici
- BENTO exemplu: trailingPE 7.57 (gresit, foloseste 2024) vs real 25.79 (TTM)

### Acceptance Criteria — Pas 5

- [x] Pentru BENTO: trailingPE si forwardPE sunt calculate din datele oficiale, nu din Yahoo
- [x] trailingPE foloseste TTM (ultimele 4 trimestre), nu anul fiscal anterior
- [x] forwardPE foloseste BVC (buget) sau e marcat ca null daca nu exista
- [ ] priceToBook e calculat din bilantul oficial, nu din Yahoo ⚠️ Doar DN momentan
- [ ] Toate metricile au `source` (yfinance / bvb.ro / excel_company / calculated)

---

## Pas 6: BVC in graficele anuale (post-MVP)

**Obiectiv:** Adaugam Bugetul de Venituri si Cheltuieli pe anul curent ca set separat de bare in graficul anual, cu o culoare distincta.

**Grafic rezultate anuale — dupa modificare:**
```
Bara albastra (existenta):    Venituri realizate istoric
Bara mov deschis (NOUA):      Venituri bugetate (an curent)
Bara verde/rosie (existenta): Profit net realizat istoric
Bara portocalie (NOUA):       Profit net bugetat (an curent)
```

- Realizat: bare solide (albastru/verde)
- Bugetat: bare cu pattern hatched sau border dashed + culoare distincta

### Acceptance Criteria — Pas 6

- [x] Graficele anuale au bare separate pentru buget (culoare distincta — fuchsia #e879f9)
- [x] Bugetul e clar diferentiat vizual de rezultatele realizate (culoare distincta)
- [x] Tooltip-ul arata "Bugetat 2026" vs "Realizat 2025"
- [x] Functioneaza pentru orice companie care are rand in tabela `bvc`

---

## Out of Scope (v1)

- Suport multi-user / autentificare
- Notificari push (email, SMS)
- Trading / order execution
- Comparatie intre companii (peer analysis)
- Export CSV/PDF rapoarte
- Integrare cu brokeri (Tradeville, IBKR)
- Mobile app (PWA e suficient pentru v1)

---

## Definitii

Vezi [CONTEXT.md](./CONTEXT.md) pentru glosarul complet.

| Termen | Definitie |
|---|---|
| **BVC** | Buget de Venituri si Cheltuieli — document publicat anual de companiile listate BVB cu proiectiile financiare pentru anul in curs. |
| **TTM** | Trailing Twelve Months — ultimele 12 luni (4 trimestre) de la cea mai recenta raportare. Folosit pentru trailingPE. |
| **Zona verde** | Singura tabela in care `company_fetcher.py` poate scrie: `price_history`. Restul sunt zona rosie (read-only). |
| **Zona rosie** | Tabelele `companies`, `quarterly`, `annual`, `bvc`, `calendar`, `calculated_metrics` — populate doar prin curatare manuala sau scraping v2. |
| **Metrici calculate** | Indicatori financiari (P/E, P/B, EPS) derivati din date brute (venituri, profit, bilant) — nu preluati ca-atare din Yahoo. |
| **WAL mode** | Write-Ahead Log — modul SQLite care permite citiri concurente in timpul scrierilor. E mai rapid si mai sigur decat rollback journal. |
