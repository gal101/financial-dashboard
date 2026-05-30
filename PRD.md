# PRD — BVB Portfolio Dashboard v1

> Product Requirements Document — MVP
> Bazat pe FEATURES.md, rafinat prin grill-with-docs
> 30 mai 2026

## Scop

Dashboard personal de investiții BVB (Bursa de Valori București). Utilizator: Andrei (single user). Self-hosted pe server personal, accesibil local/Tailscale.

## MVP Scope (Milestone 1)

Trei livrabile independente, în ordinea priorității:

| # | Feature | Dependențe |
|---|---------|------------|
| 1 | **Company Profile v1** | `company_data.json` (există), `company_fetcher.py` (există) |
| 2 | **Watchlist** | Fișier nou `watchlist.json` |
| 3 | **Stiri** | Nimic (link extern Google News) |

**NU intră în v1** (rămân în FEATURES.md ca backlog):
- **PE chart istoric** — grafic P/E evolutiv (v2)
- Buget overlay + Forward P/E estimat (v2)
- Calendar financiar (v2, necesită scraping BVB.ro)
- Istoric tranzacții (import CSV)
- Benchmark BET Index
- Alerte de preț
- Chat AI

**Notă pentru v2:** Adăugarea profilului unei companii noi (cu PE istoric, bugete, forward PE) poate deveni un proces semi-manual — un skill de agent care face research pe net, calculează metrici, și populează datele.

---

## 1. Company Profile v1

### User Story
> Ca investitor, când dau click pe un simbol din portofoliu sau watchlist, vreau să văd o pagină dedicată cu toate detaliile companiei — metrici, grafic preț, rezultate financiare.

### Arhitectură

- **Fișier nou:** `company.html?symbol=TLV`
- **CSS comun:** `style.css` (extras din dashboard.html, folosit de ambele pagini)
- Routing: parametru `?symbol=` din URL determină ce companie se afișează
- Navigare: back button către dashboard.html
- Link din dashboard: click pe simbol → `company.html?symbol=TLV`

### Secțiuni

#### 1.1 Antet + Metrici

```
┌─────────────────────────────────────────────┐
│ ← Înapoi la portofoliu                       │
│                                               │
│ TLV — Banca Transilvania                      │
│ Sector: Banking | Industrie: Banks—Regional   │
│ Preț: 37.62 RON  ▼ -1.0%                     │
│                                               │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│ │ Market   │ │ P/E      │ │ Marja    │       │
│ │ Cap      │ │ (TTM)    │ │ profit   │       │
│ │ 15.4B    │ │ 8.2      │ │ 38.5%    │       │
│ └──────────┘ └──────────┘ └──────────┘       │
│                                               │
│ ┌──────────┐ ┌──────────┐                    │
│ │ Forward  │ │ Dividend │  (doar dacă există) │
│ │ P/E      │ │ Yield    │                    │
│ │ 6.5      │ │ 4.2%     │                    │
│ └──────────┘ └──────────┘                    │
└─────────────────────────────────────────────┘
```

**Metrici target** (afișate doar dacă există în date):
1. Market Cap
2. P/E (TTM)
3. Forward P/E
4. Dividend Yield
5. Marja profit

**Regulă:** cardul nu se afișează dacă valoarea e `None`/lipsește. Fără placeholder-uri goale.

**Sursă:** `company_data.json` → `companies[simbol].metrics`

#### 1.2 Grafic Preț

- **Tip:** line chart (doar linia prețului, fără volum)
- **Selector perioadă:** 5Y / 3Y / 1Y / 6L / 3L / 1L / 1S / 1Z
- **Default:** 1 an
- **Sursă:** `company_data.json` → `companies[simbol].price_history`
- **Librărie:** Chart.js (deja folosit în dashboard.html)

#### 1.3 Rezultate Trimestriale

- **Tip:** bar chart — venituri + profit net
- **Perioadă:** ultimele 12 trimestre (dacă există)
- **Culori:** albastru pentru venituri, verde/roșu pentru profit
- **Scroll:** dacă 12 trimestre nu încap pe ecran, container cu scroll orizontal
- **Sursă:** `company_data.json` → `companies[simbol].quarterly`
- **Fallback:** dacă nu există date trimestriale, se afișează „Date indisponibile"

#### 1.4 Descriere Companie

- Text descriptiv (business summary)
- **Sursă:** `company_data.json` → `companies[simbol].metrics.longBusinessSummary`

---

## 2. Watchlist

### User Story
> Ca investitor, vreau să urmăresc companii pe care nu le dețin încă, să le văd prețul curent și să pot naviga la profilul lor complet.

### Detalii

- **Fișier:** `watchlist.json` — array de simboluri
- **Git:** ✅ committable (nu conține date personale)
- **UI:** tabel separat pe dashboard.html (sub holdings), sau secțiune colapsabilă
- **Acțiuni:**
  - Adaugă simbol (input field + buton)
  - Click pe simbol → `company.html?symbol=X`
  - Șterge din watchlist

### Structură `watchlist.json`

```json
{
  "simbols": ["H2O", "WINE", "M", "SNG"]
}
```

### Prețuri Live

Watchlist-ul beneficiază de același refresh live din browser ca și holdings (Yahoo Finance API client-side).

---

## 3. Stiri

### User Story
> Ca investitor, când mă uit la o companie, vreau să pot accesa rapid știri recente despre ea.

### Implementare

Link extern către Google News cu query pre-populat:

```
https://news.google.com/search?q=Banca+Transilvania+BVB&hl=ro
```

- Afișat ca link/buton în Company Profile
- Se deschide în tab nou

---

## Arhitectură Finală (v1)

```
/financial-dashboard/
├── dashboard.html          # Portfolio overview + Watchlist
├── company.html            # Company Profile (nou)
├── style.css               # CSS comun (nou, extras din dashboard)
├── portfolio_updater.py    # Actualizare prețuri (existent)
├── company_fetcher.py      # Fetch date companii (existent)
├── bvb_portfolio.json      # Dețineri reale ❌ gitignorat
├── bvb_portfolio.example.json  # Structură anonimizată
├── company_data.json       # Date publice companii
├── watchlist.json          # Simboluri urmărite (nou)
├── FEATURES.md             # Backlog complet
├── PRD.md                  # Acest document
├── CONTEXT.md              # Glosar de termeni
└── .gitignore
```

### Flux de date

```
[yfinance API] ←── company_fetcher.py ──→ company_data.json ──→ company.html
                             │
[yfinance API] ←── portfolio_updater.py ──→ bvb_portfolio.json ──→ dashboard.html
                                                                ──→ company.html
[manual] ───────── watchlist.json ──────────────────────────────→ dashboard.html
```

---

## Acceptance Criteria (Milestone 1)

### Company Profile
- [ ] Click pe simbol în dashboard → navigare la `company.html?symbol=X`
- [ ] Antet: simbol, nume, sector, industrie, preț + variație
- [ ] Carduri cu metrici (doar cele disponibile)
- [ ] Grafic preț cu selector de perioadă (funcțional)
- [ ] Rezultate trimestriale (bar chart, 8Q)
- [ ] Descriere companie
- [ ] Back button → dashboard
- [ ] Link Google News (tab nou)

### Watchlist
- [ ] Input field + buton „Adaugă"
- [ ] Tabel cu simbolurile din watchlist, preț curent
- [ ] Click pe simbol → Company Profile
- [ ] Buton ștergere simbol

### Transversal
- [ ] CSS comun în `style.css`
- [ ] Dashboard.html extrage CSS-ul în `style.css` (fără breaking changes)
- [ ] `watchlist.json` inițializat cu array gol
- [ ] Nimic din ce e în `.gitignore` nu ajunge în commit

---

## Definiții

Vezi [CONTEXT.md](./CONTEXT.md) pentru glosarul complet de termeni.
