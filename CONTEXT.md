# CONTEXT.md — BVB Portfolio Dashboard

> Glosar de termeni pentru domeniul de investitii BVB.
> Acest fisier defineste limbajul comun al proiectului.
> Fara detalii de implementare.

## Entitati

| Termen | Definitie |
|---|---|
| **Portfolio** | Detinerile reale ale utilizatorului (actiuni + produse structurate), cu cantitati si preturi de achizitie. Sursa: `bvb_portfolio.json`. |
| **Holding** | O pozitie individuala din portofoliu — un simbol cu o cantitate detinuta, pret de achizitie, valoare curenta, P/L. |
| **Watchlist** | Lista de simboluri urmarite de utilizator dar **fara detinere**. Separat de Portfolio. |
| **Company Profile** | Sectiunea cu detaliile unei singure companii: metrici financiare, grafice de pret, rezultate financiare. Accesibila atat din Holdings cat si din Watchlist. |
| **Simbol** | Ticker-ul BVB al companiei (ex: `TLV`, `SNP`, `BENTO`). Se stocheaza **fara** sufix `.RO`. Sufixul `.RO` se adauga doar in request-urile catre Yahoo Finance. |
| **Produs structurat** | Certificate turbo (ex: `EBTLVTL19`). Nu sunt listate pe Yahoo Finance — pretul de referinta e cel din exportul brokerului. |

## Concepte financiare

| Termen | Definitie |
|---|---|
| **Pret actual** | Ultimul pret de tranzactionare de pe BVB, obtinut prin Yahoo Finance (campul `regularMarketPrice`). |
| **Pret mediu de achizitie** | Pretul mediu ponderat la care utilizatorul a cumparat actiunile. |
| **Investitie initiala** | `cantitate × pret_mediu_achizitie`. Suma efectiv investita in acea pozitie. |
| **Valoare evaluata** | `cantitate × pret_actual`. Cat valoreaza pozitia la pretul curent. |
| **P/L (Profit/Pierdere)** | `valoare_evaluata − investitie_initiala`. Nerealizat (pozitia e inca deschisa). |
| **P/L Realizat** | Profitul sau pierderea dintr-o pozitie **inchisa** (vanduta complet). |
| **Total buzunar** | `investitie_initiala_totala + |pierderi_realizate|`. Suma totala scoasa din buzunar, incluzand banii pierduti la pozitii inchise. |
| **Randament total** | `(valoare_evaluata_totala − total_buzunar) / total_buzunar × 100`. |
| **Pondere** | `valoare_evaluata / valoare_evaluata_totala × 100`. Cat la suta din portofoliu reprezinta pozitia. |

## Surse de date

| Sursa | Ce furnizeaza |
|---|---|
| **Yahoo Finance** (yfinance) | Preturi curente, istoric preturi, metrici (P/E, market cap, etc.), rezultate financiare trimestriale/anuale. |
| **Tradeville CSV** | Portofoliul initial: simboluri, cantitati, preturi de achizitie. Importat o singura data. |
| **BVB.ro scraping** (viitor) | Calendar financiar, bugete anuale, link-uri Investor Relations. |
