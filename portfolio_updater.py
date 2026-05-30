#!/usr/bin/env python3
"""
BVB Portfolio Price Updater
============================
Fetches current prices from Yahoo Finance using yfinance (.RO suffix for BVB).
Updates bvb_portfolio.json and re-injects into dashboard.html.

Usage:
    python3 portfolio_updater.py          # normal (skips weekends)
    python3 portfolio_updater.py --force  # force even on weekends
    python3 portfolio_updater.py --dry-run
"""

import json
import os
import sys
from datetime import datetime, timezone

# Bootstrap: ensure yfinance is available via our venv
VENV_PYTHON = "/opt/data/.venv/bin/python3"
if sys.executable != VENV_PYTHON:
    import subprocess
    result = subprocess.run([VENV_PYTHON, __file__] + sys.argv[1:])
    sys.exit(result.returncode)

import yfinance as yf

# Config — everything in /financial-dashboard/
BASE_DIR = "/financial-dashboard"
JSON_FILE = os.path.join(BASE_DIR, "bvb_portfolio.json")


YAHOO_SUFFIX = ".RO"


def yahoo_symbol(simbol):
    """Map BVB symbol to Yahoo Finance format. Returns None if not available."""
    if simbol.startswith("EBTLV"):
        return None
    return f"{simbol}{YAHOO_SUFFIX}"


def fetch_price(simbol):
    """Fetch current price from Yahoo Finance. Returns dict or None.
    
    Uses regularMarketPrice (last trade price) as the current price,
    and regularMarketPreviousClose for change calculation.
    Falls back to fast_info if info fields are unavailable.
    """
    ysym = yahoo_symbol(simbol)
    if ysym is None:
        return None
    try:
        ticker = yf.Ticker(ysym)
        # Prefer info dict for accurate regular market values
        info = ticker.info
        price = info.get("regularMarketPrice")
        prev = info.get("regularMarketPreviousClose")
        
        # Fallback to fast_info if info is empty (rate limit, etc.)
        if price is None:
            fi = ticker.fast_info
            price = fi.last_price
            prev = fi.previous_close or price
        
        if price is None:
            return None
        
        if prev is None:
            prev = price
        
        change_pct = ((price - prev) / prev * 100) if prev else 0.0
        return {
            "price": round(float(price), 4),
            "change_pct": round(float(change_pct), 2),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"  ! {simbol}: {e}")
        return None


def is_weekday():
    """Check if today is a weekday in EEST (UTC+2)."""
    now = datetime.now(timezone.utc)
    return now.weekday() < 5, (now.hour + 2) % 24, now


def load_portfolio():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_portfolio(data):
    # Save to main portfolio file
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Also save to portfolio_data.json served by nginx
    data_file = os.path.join(BASE_DIR, "portfolio_data.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def print_summary(portfolio):
    m = portfolio["metadata"]
    pnl = m["total_profit_pierdere_RON"]
    sign = "+" if pnl >= 0 else ""
    emoji = "[+]" if pnl >= 0 else "[-]"
    print()
    print("-" * 50)
    print("PORTOFOLIU ACTUALIZAT")
    print("-" * 50)
    print(f"  Investit:  {m['total_investit_RON']:>12,.2f} RON")
    print(f"  Valoare:   {m['total_evaluare_RON']:>12,.2f} RON")
    print(f"  {emoji} P/L:     {sign}{pnl:>+11,.2f} RON  ({sign}{m['return_total_pct']}%)")
    print("-" * 50)
    print(f"  {m.get('last_price_update', 'N/A')}")
    print()


def main():
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    weekday, eest_hour, now = is_weekday()

    if not weekday and not force:
        print(f"Weekend (EEST {eest_hour:02d}:{now.minute:02d}) -- piata inchisa. --force pentru a forta.")
        sys.exit(0)

    print(f"Actualizare preturi BVB -- {now.strftime('%Y-%m-%d %H:%M:%S')} UTC  (EEST {eest_hour:02d}:{now.minute:02d})")
    print()

    portfolio = load_portfolio()
    symbols = [h["simbol"] for h in portfolio["holdings"]]
    prices = {}

    for sym in symbols:
        result = fetch_price(sym)
        if result:
            prices[sym] = result
            print(f"  [OK] {sym:12s} {result['price']:>10.4f} RON  ({result['change_pct']:+.2f}%)")
        else:
            print(f"  [--] {sym:12s} (fara Yahoo, pastreaza referinta)")

    if dry_run:
        print("\nDry run -- nimic modificat.")
        sys.exit(0)

    # Update holdings
    updated = 0
    for h in portfolio["holdings"]:
        sym = h["simbol"]
        if sym in prices:
            p = prices[sym]
            h["pret_actual_RON"] = p["price"]
            h["variatie_pret_pct"] = p["change_pct"]
            h["valoare_evaluata_RON"] = round(h["actiuni"] * p["price"], 2)
            h["profit_pierdere_RON"] = round(
                h["valoare_evaluata_RON"] - h["investitie_initiala_RON"], 2
            )
            h["pret_updated_at"] = p["updated_at"]
            updated += 1

    # Recalculate metadata
    m = portfolio["metadata"]
    m["total_evaluare_RON"] = round(
        sum(h["valoare_evaluata_RON"] for h in portfolio["holdings"]), 2
    )
    m["total_profit_pierdere_RON"] = round(
        sum(h["profit_pierdere_RON"] for h in portfolio["holdings"]), 2
    )
    m["return_total_pct"] = round(
        m["total_profit_pierdere_RON"] / m["total_investit_RON"] * 100, 2
    )
    m["last_price_update"] = datetime.now(timezone.utc).isoformat()

    save_portfolio(portfolio)
    print_summary(portfolio)
    print(f"  Preturi actualizate: {updated}/{len(symbols)}")
    # Also refresh company financial data
    import subprocess
    print("\nActualizare si date financiare...")
    subprocess.run([sys.executable, os.path.join(BASE_DIR, "company_fetcher.py")])
    print("Gata!")


if __name__ == "__main__":
    main()
