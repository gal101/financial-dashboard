# CONTEXT.md — BVB Portfolio Dashboard

> Glosar de termeni pentru domeniul de investitii BVB.
> Acest fisier defineste limbajul comun al proiectului.
> Fara detalii de implementare.

## Entitati

| Termen | Definitie |
|---|---|
| **Portfolio** | Detinerile reale ale utilizatorului (actiuni + produse structurate), cu cantitati si preturi de achizitie. Sursa: baza de date privata `user_data.db` populata automat din Tradeville. |
| **Holding** | O pozitie individuala din portofoliu — un simbol cu o cantitate detinuta, pret de achizitie, valoare curenta, P/L. Are si un camp `tip` (`actiuni` sau `struct`) preluat direct de la broker. |
| **Watchlist** | Lista de simboluri urmarite de utilizator dar **fara detinere**. Separat de Portfolio. ✅ Implementat. |
| **Company Profile** | Sectiunea cu detaliile unei singure companii: metrici financiare, grafice de pret, rezultate financiare. Accesibila atat din Holdings cat si din Watchlist. |
| **Simbol** | Ticker-ul BVB al companiei (ex: `TLV`, `SNP`, `BENTO`). Se stocheaza **fara** sufix `.RO`. |
| **Produs structurat** | Certificate turbo (ex: `EBTLVTL19`). Nu sunt listate in cotațiile principale — pretul de referinta e cel din exportul brokerului sau feed live. |

## Concepte financiare

| Termen | Definitie |
|---|---|
| **Pret actual** | Ultimul pret de tranzactionare de pe BVB, obtinut prin Tradeville API (WebSocket/HTTP proxy) sau cache SQLite. |
| **Pret mediu de achizitie** | Pretul mediu ponderat la care utilizatorul a cumparat actiunile. |
| **Investitie initiala** | `cantitate × pret_mediu_achizitie`. Suma efectiv investita in acea pozitie. |
| **Valoare evaluata** | `cantitate × pret_actual`. Cat valoreaza pozitia la pretul curent. |
| **P/L (Profit/Pierdere)** | `valoare_evaluata − investitie_initiala`. Profitul Nerealizat (pe detinerile inca deschise). |
| **P/L Realizat** | Suma profiturilor (sau pierderilor) extrase din istoric, adica pe pozitii de vanzare (extrase direct din campul `profit` din Tradeville API). |
| **Dividende** | Suma totala a dividendelor incasate istoric in cont. |
| **Real Profit/Loss** | `P/L nerealizat + P/L realizat + Dividende`. Profitul net total, incluzand istoric absolut si valorile curente de piata. |
| **Pondere** | `valoare_evaluata / valoare_evaluata_totala × 100`. Cat la suta din portofoliu reprezinta pozitia. |

## Surse de date

| Sursa | Ce furnizeaza |
|---|---|
| **Tradeville API** | Preturi live curente (WebSocket ticks), istoric cotații zilnice, metrici brute (SharesNr, Earnings, Name, ISIN). |
| **Site-uri oficiale companii** (Investor Relations) | Rapoarte financiare (Excel/PDF), Bugete de Venituri si Cheltuieli (BVC), numar de actiuni. Sursa primara pentru datele financiare brute. |
| **BVB.ro** | Pagina simbol (PER, PBV, EPS, DIVY — valori publicate oficial), calendar financiar. |
| **Sincronizare Automata** | Portofoliul si tranzactiile anterioare (inclusiv profitul istoric pe actiunile vandute) sunt sincronizate continuu din endpoint-urile Tradeville `Activity` si `Portfolio` prin `activity_sync.py`. |
| **metrics_calculator.py** (intern) | Calculeaza trailingPE, forwardPE, EPS din datele brute extrase din Excel-uri/PDF-uri. Nu ne bazam pe Yahoo pentru aceste metrici. |
| **bvc_parser.py** (intern) | Parseaza fisiere Excel (.xlsx) si PDF pentru a extrage BVC (buget) si date financiare brute. |

## Metrici financiare (calculate intern)

| Termen | Definitie | Formula |
|---|---|---|
| **TTM** | Trailing Twelve Months — ultimele 12 luni (4 trimestre) de la cea mai recenta raportare. | Suma ultimelor 4 trimestre dupa data. |
| **trailingPE (calculat)** | P/E bazat pe TTM, nu pe anul fiscal anterior. ✅ Calculat pentru 9 companii. | `marketCap / TTM_net_income` |
| **forwardPE (calculat)** | P/E forward bazat pe BVC (buget), nu pe estimari de analisti (inexistente pentru BVB). ✅ Calculat pentru 6 companii cu BVC. | `marketCap / bvc.net_income`. Daca BVC lipseste, e `null`. |
| **priceToBook (calculat)** | P/B din bilantul oficial. ⚠️ Doar DN are valoare momentan. | `marketCap / total_equity` (din bilant, nu din Yahoo). |
| **EPS (calculat)** | Earnings per share TTM. | `TTM_net_income / shares_outstanding` (numar actiuni din BVB.ro). |
| **BVC** | Buget de Venituri si Cheltuieli — document publicat anual de companiile listate BVB cu proiectiile financiare pentru anul in curs. Contine venituri bugetate, cheltuieli, profit brut/net estimat. ✅ Extras pentru 7 companii. | — |
