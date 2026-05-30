# BVB Portfolio Dashboard — Plan features

> Document de planificare, v1.2
> 29 mai 2026

---

## Cuprins

1. [Company Profile](#1-company-profile)
   1.1 [Antet + metrici](#11-antet--metrici)
   1.2 [Price chart + PE chart](#12-price-chart--pe-chart)
   1.3 [Volum tranzactionat](#13-volum-tranzactionat)
   1.4 [Rezultate trimestriale (12 trimestre)](#14-rezultate-trimestriale-12-trimestre)
   1.5 [Rezultate anuale + buget overlay](#15-rezultate-anuale--buget-overlay)
   1.6 [Forward PE estimat](#16-forward-pe-estimat)
   1.7 [Calendar financiar + urmatorul eveniment](#17-calendar-financiar--urmatorul-eveniment)
   1.8 [Link site companie (IR)](#18-link-site-companie-ir)
   1.9 [Chat AI floating window](#19-chat-ai-floating-window)
2. [Stiri + articole](#2-stiri--articole)
3. [Benchmark vs BET Index](#3-benchmark-vs-bet-index)
4. [Alocare pe sectoare](#4-alocare-pe-sectoare)
5. [Watchlist](#5-watchlist)
6. [Dividend tracker](#6-dividend-tracker)
7. [Istoric tranzactii](#7-istoric-tranzactii)
8. [Alerte de pret](#8-alerte-de-pret)

---

## 1. Company Profile

La click pe un simbol din tabel, se deschide un view dedicat companiei cu:

### 1.1 Antet + metrici

- **Antet:** simbol, nume companie, sector, industrie, pret curent + variatie
- **Scurta descriere** a companiei (business summary)
- **Carduri cu metrici cheie** (din yfinance info):
  - Market Cap
  - P/E (TTM)
  - Forward P/E
  - P/B
  - Dividend Yield
  - Beta
  - ROE, ROA
  - Marja profit
  - Crestere venituri / profit
  - Free Cash Flow
  - D/E, P/S

### 1.2 Price chart + PE chart

Doua grafice **in paralel**, unul deasupra celuilalt, controlate de acelasi selector de perioada.

**Selector perioada:** 5y, 3y, 1y, 6 luni, 3 luni, 1 luna, 1 sapt, 1 zi.
Default: 1 an. Schimbarea perioadei actualizeaza ambele grafice simultan.

**Grafic 1 — Evolutie pret:**
- Linia pretului de inchidere zilnic

**Grafic 2 — P/E istoric:**
- P/E = pret / EPS trailing 12 luni (suma ultimelor 4 trimestre)
- Se actualizeaza: zilnic (pretul se schimba) + trimestrial (cand apar rezultatele)
- Rezulta un grafic cu variatie zilnica mica, dar salturi la fiecare raportare de earnings
- Pentru perioade mai mari de 1 an: se poate calcula P/E pe baza EPS-ului anual

**Sursa datelor:** yfinance — `ticker.history(period=X)` pentru pret, `ticker.quarterly_financials` pentru EPS (de unde calculam TTM EPS).

**Fezabilitate:** Toate perioadele sunt disponibile prin yfinance gratis.

### 1.3 Volum tranzactionat

Se pastreaza, dar nu e prioritar. Grafic bar chart cu volumul zilnic pentru aceeasi perioada selectata.

### 1.4 Rezultate trimestriale (12 trimestre)

Ultimele **12 trimestre**. Bar charts pentru:

- **Venituri trimestriale** — bar chart
- **Profit net trimestrial** — bar chart cu culori diferite (verde profit, rosu pierdere)

**Datele:** yfinance ofera suficiente trimestre pentru majoritatea companiilor BVB mai mari. Pentru companii mai mici (BENTO, SAFE) probabil nu avem deloc — se afiseaza mesaj "Date indisponibile".

### 1.5 Rezultate anuale + buget overlay

**Grafic anual:** Venituri anuale pe ultimii 3-5 ani (bar chart).

**Overlay buget:** O linie pe fiecare bara care arata **cat a bugetat compania** fata de cat a realizat.

**Verdict:** Pe baza diferentei dintre buget si realizat pe ultimii ani, sistemul estimeaza daca compania:
- **Bugeteaza precaut** — livreaza peste buget (realizeaza >105%)
- **Bugeteaza optimist** — livreaza sub buget (realizeaza <95%)
- **Bugeteaza balansat** — livreaza aproape de buget (95-105%)

**Sursa datelor de buget:** Scraping de pe BVB.ro sau de pe site-urile companiilor (pagina Investor Relations). Unele companii nu publica deloc bugete — pentru acelea, overlay-ul nu se afiseaza.

**Infrastructura scraping:** Va fi nevoie de un container separat cu un browser headless (Playwright/Chromium) la care Hermes sa aiba acces pentru a rula scripturile de scraping. Andrei se ocupa de setup-ul containerului.

### 1.6 Forward PE estimat

Pe baza istoricului de acuratete a bugetarilor, se calculeaza:

1. **Rata medie de realizare a bugetului** (de ex. 80% din buget se realizeaza)
2. **EPS estimat pentru anul curent** = (bugetul pe anul curent EPS * rata de realizare)
3. **Forward P/E estimat** = pret curent / EPS estimat
4. **Pret tinta** = daca piata ar pretui compania la P/E-ul sau istoric mediu, atunci pret tinta = P/E mediu istoric * EPS estimat
5. **Randament potential** = (pret tinta - pret curent) / pret curent

**Output:** Card cu "Forward P/E estimat: X.x", "Pret tinta estimat: Y.YY RON (+Z%)", "Rata de realizare buget: W%"

**Observatie:** Totul depinde de existenta datelor de buget (vezi 1.5). Daca nu avem buget, nu putem calcula forward P/E estimat.

### 1.7 Calendar financiar + urmatorul eveniment

O sectiune care arata:

- **Urmatorul eveniment financiar** — "Publicare rezultate Q2 2026: 15 august 2026 (peste 78 de zile)"
- **Lista evenimentelor viitoare** — raportari trimestriale, AGA, plata dividende

**Sursa:** Scraping de pe BVB.ro (are calendar financiar per companie) sau de pe site-urile companiilor. Aceeasi infrastructura de browser ca la punctul 1.5.

### 1.8 Link site companie (IR)

In loc de link Yahoo Finance, link direct catre **pagina de Investor Relations** a companiei.

**Implementare:** Scraping pentru a identifica URL-ul corect al paginii IR pentru fiecare companie din portofoliu. Se salveaza in configuratie dupa identificare.

**Alternativa:** yfinance are campul `website` in info dict — putem incerca sa derivam linkul IR (ex: `site.com/investitori` sau `site.com/investor-relations`).

### 1.9 Chat AI floating window

**Prioritate: CEA MAI MICA.** Andrei poate vorbi cu orice AI despre companii de pe telefon, deci feature-ul asta e ultimul pe lista. Nu il planificam acum.

---

## 2. Stiri + articole

O sectiune in profilul companiei cu linkuri la articole relevante.

**Implementare initiala:** Link direct catre Google News cu query pre-populat (nume companie + "BVB"). Gratis, instant, fara configurare.

**Viitor:** Daca vrem sumarizare sau mai multe surse, putem adauga NewsAPI sau scraping.

---

## 3. Benchmark vs BET Index

Compara portofoliul cu BET pe aceeasi perioada.

**Sursa:** yfinance — simbolul `^BET.BX` pentru BET Index.
**Implementare:** Grafic cu 2 linii (portofoliu vs BET), normalizat la 100 la data de start. Butoane de perioada.

---

## 4. Alocare pe sectoare

Pie chart cu distributia portofoliului pe sectoare economice.
- Banking (TLV)
- IT (BENTO, SAFE)
- Energie (SNP, PE)
- Agricultura (DN)
- Turbo/Structurate (EBTLVTL19)

**Sursa datelor:** yfinance — `info.sector` pentru fiecare companie. Datele exista deja.

---

## 5. Watchlist

Lista de companii urmarite (fara detinere). Se salveaza in JSON.
- Input field pentru adaugat simbol
- Pret curent + variatie
- Optional: target price cu alerta vizuala

---

## 6. Dividend tracker

- Randament dividend curent (yfinance: `info.dividendYield`)
- Istoric dividende (yfinance: `ticker.dividends`)
- Calendar: urmatorul ex-date (daca avem date din scraping)

---

## 7. Istoric tranzactii

Import CSV cu tranzactiile → fisier JSON. Tabel cu istoric, calcul cost basis corect.
Andrei a trimis deja CSV-ul pe Telegram.

---

## 8. Alerte de pret

Notificare (Telegram) cand o actiune atinge un pret target.

**Trade-off:** Frecventa vs rate limiting yfinance.
- 1 check/ora in timpul sedintei = ~9 checkuri/zi = ~63 requesturi (rezonabil)
- Sau doar la deschidere + inchidere (mai safe)

**Decizie:** Amanam discutia pana avem restul functional.

---

## Arhitectura generala

```
[Browser container (viitor)]
    |  Playwright scraping
    v
BVB.ro + site-uri companii
    |
    | (date buget, calendar, IR links)
    v
[company_data.json] ──── yfinance (preturi, financiare, metrici)
    |
    v
[dashboard.html] (static, servit de nginx)
    |
    |-- Portfolio overview (tabele, KPI-uri, grafice)
    |-- Company Profile (modal, la click pe simbol)
         |-- Price + PE charts (Chart.js)
         |-- Financial results (quarterly + annual)
         |-- Budget overlay (daca datele exista)
         |-- Calendar
         |-- News links
```

## 🔒 Securitatea datelor personale

**NU commita niciodata fisierul cu detinerile reale:**

- `bvb_portfolio.json` — contine portofoliul real (numar actiuni, pret achizitie, sume investite, P/L)

Acest fisier este listat in `.gitignore` si **nu va fi urcat pe GitHub**.

### Cum pornesti proiectul pe un server nou

1. Cloneaza repo-ul
2. Copiaza `bvb_portfolio.example.json` in `bvb_portfolio.json`
3. Editeaza `bvb_portfolio.json` cu datele tale reale
4. Ruleaza `portfolio_updater.py` pentru a genera preturile actualizate

### Ce e safe de commit

- `bvb_portfolio.example.json` — structura anonimizata (fara date reale)
- `company_data.json` — date publice despre companii (market cap, sector, etc.)
- `dashboard.html`, `*.py` — codul aplicatiei
- `FEATURES.md` — documentatia

---

## Prioritate finala (ordonata)

1. **Company Profile base** — metrici, price chart, PE chart, selector perioada, rezultate trimestriale 12Q, rezultate anuale, link site IR
2. **Stiri** — Google News link (simplu)
3. **Sector allocation** — usor de facut
4. **Dividend tracker** — usor de facut
5. **Watchlist** — simplu
6. **Benchmark BET** — mediu
7. **Istoric tranzactii** — mediu (import CSV + UI)
8. **Scraping container setup** — conditie pentru:
   - Buget overlay + forward PE
   - Calendar financiar
   - Link-uri IR automate
9. **Alerte de pret** — dupa ce avem scraping
10. **Chat AI** — ultimul, poate niciodata
