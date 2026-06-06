"""
One-shot migration: JSON → SQLite.
Run once. Safe to re-run (uses INSERT OR REPLACE).
"""
import json, os, sys, math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from db import (
    get_db, init_db, upsert_company, upsert_prices, upsert_quarterly,
    upsert_annual, upsert_bvc, upsert_calendar, upsert_metrics,
    update_market_cap, sanitize_val
)
from metrics_calculator import recalculate_metrics


def migrate():
    conn = get_db()
    init_db(conn)

    # ── 1. Load company_data.json ──
    with open(os.path.join(os.path.dirname(SCRIPT_DIR), "data", "company_data.json")) as f:
        cdata = json.load(f)

    # ── 2. Load portfolio for names ──
    portfolio_names = {}
    pf_path = os.path.join(os.path.dirname(SCRIPT_DIR), "data", "bvb_portfolio.json")
    if os.path.exists(pf_path):
        with open(pf_path) as f:
            portfolio = json.load(f)
        for h in portfolio.get("holdings", []):
            portfolio_names[h["simbol"]] = h["nume"]

    # ── 3. Insert companies ──
    for symbol, comp in cdata["companies"].items():
        m = comp.get("metrics", {})
        name = comp.get("nume") or portfolio_names.get(symbol, symbol)
        upsert_company(
            conn, symbol, name,
            sector=m.get("sector"),
            industry=m.get("industry"),
            shares_outstanding=m.get("sharesOutstanding"),
            market_cap=m.get("marketCap"),
        )

    # ── 4. Insert price_history ──
    for symbol, comp in cdata["companies"].items():
        prices = comp.get("price_history", [])
        if prices:
            n = upsert_prices(conn, symbol, prices)
            print(f"  {symbol}: {n} prices")

    # ── 5. Insert quarterly (only if has data) ──
    for symbol, comp in cdata["companies"].items():
        q = comp.get("quarterly", [])
        if q:
            entries = []
            for x in q:
                items = x.get("items", {})
                entries.append({
                    "date": x["date"][:10],
                    "revenue": items.get("Total Revenue"),
                    "net_income": items.get("Net Income"),
                    "source": x.get("_note") or x.get("source"),
                })
            upsert_quarterly(conn, symbol, entries)
            print(f"  {symbol}: {len(entries)} quarterly")

    # ── 6. Insert annual ──
    for symbol, comp in cdata["companies"].items():
        a = comp.get("annual", [])
        if a:
            entries = []
            for x in a:
                items = x.get("items", {})
                entries.append({
                    "date": x["date"][:10],
                    "revenue": items.get("Total Revenue"),
                    "net_income": items.get("Net Income"),
                    "source": x.get("_note") or x.get("source"),
                })
            upsert_annual(conn, symbol, entries)
            print(f"  {symbol}: {len(entries)} annual")

    # ── 7. Insert BVC ──
    for symbol, comp in cdata["companies"].items():
        bvc = comp.get("bvc")
        if bvc and bvc.get("revenue") and bvc.get("year"):
            upsert_bvc(conn, symbol, bvc)
            print(f"  {symbol}: BVC {bvc['year']}")

    # ── 8. Insert calendar ──
    for symbol, comp in cdata["companies"].items():
        cal = comp.get("calendar", [])
        if cal:
            upsert_calendar(conn, symbol, cal)
            print(f"  {symbol}: {len(cal)} calendar events")

    # ── 9. Calculate & insert metrics ──
    from metrics_calculator import recalculate_metrics
    for symbol in cdata["companies"]:
        # Recalculate from what we have
        comp = cdata["companies"][symbol]
        calc = recalculate_metrics(comp)
        metrics = comp.get("metrics", {})
        
        result = {
            "trailing_pe": calc.get("trailingPE") or metrics.get("trailingPE"),
            "forward_pe": calc.get("forwardPE") or metrics.get("forwardPE"),
            "eps": calc.get("eps") or metrics.get("eps"),
            "profit_margin": metrics.get("profitMargins"),
            "price_to_book": calc.get("priceToBook") or metrics.get("priceToBook"),
            "dividend_yield": metrics.get("dividendYield"),
        }
        upsert_metrics(conn, symbol, result)
        print(f"  {symbol}: P/E={result['trailing_pe']}")

    conn.commit()
    
    # ── 10. Summary ──
    print(f"\n=== MIGRATION COMPLETE ===")
    for symbol in sorted([r[0] for r in conn.execute("SELECT symbol FROM companies").fetchall()]):
        pq = conn.execute("SELECT COUNT(*) FROM price_history WHERE symbol=?", (symbol,)).fetchone()[0]
        qq = conn.execute("SELECT COUNT(*) FROM quarterly WHERE symbol=?", (symbol,)).fetchone()[0]
        qa = conn.execute("SELECT COUNT(*) FROM annual WHERE symbol=?", (symbol,)).fetchone()[0]
        qb = conn.execute("SELECT COUNT(*) FROM bvc WHERE symbol=?", (symbol,)).fetchone()[0]
        qc = conn.execute("SELECT COUNT(*) FROM calendar WHERE symbol=?", (symbol,)).fetchone()[0]
        m = conn.execute("SELECT * FROM calculated_metrics WHERE symbol=?", (symbol,)).fetchone()
        pe = f"{m['trailing_pe']:.2f}" if m and m['trailing_pe'] else "N/A"
        print(f"  {symbol:6s}: P/E={pe:>8s} | Q={qq} A={qa} | Prices={pq} | BVC={qb} Cal={qc}")

    conn.close()


if __name__ == "__main__":
    migrate()
