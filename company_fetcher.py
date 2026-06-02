#!/usr/bin/env python3
"""
Fetch daily price history and company metadata from Tradeville and write to SQLite.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, date, timedelta

# Bootstrap to venv
VENV_PYTHON = "/opt/data/.venv/bin/python3"
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    import subprocess
    result = subprocess.run([VENV_PYTHON, __file__] + sys.argv[1:])
    sys.exit(result.returncode)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "server"))

from db import get_db, upsert_prices, upsert_company, sanitize_val
from shared.tradeville_client import TradevilleClient

PORTFOLIO_FILE = os.path.join(SCRIPT_DIR, "bvb_portfolio.json")
WATCHLIST_FILE = os.path.join(SCRIPT_DIR, "watchlist.json")

def main():
    conn = get_db()
    symbols_seen = set()
    total_prices = 0

    # Parse targeted tickers
    target_tickers = [arg.upper() for arg in sys.argv[1:] if not arg.startswith("--")]

    # Load portfolio symbols
    portfolio_symbols = []
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                portfolio = json.load(f)
            portfolio_symbols = [h["simbol"] for h in portfolio.get("holdings", [])]
        except Exception as e:
            print(f"Error loading portfolio symbols: {e}")

    # Load watchlist symbols
    watchlist_symbols = []
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                wl = json.load(f)
            watchlist_symbols = wl.get("simbols", [])
        except Exception as e:
            print(f"Error loading watchlist symbols: {e}")

    # Combine and filter
    all_symbols = list(dict.fromkeys(portfolio_symbols + watchlist_symbols))
    if target_tickers:
        all_symbols = [sym for sym in all_symbols if sym in target_tickers]

    five_years_ago = date.today() - timedelta(days=5*365)

    print(f"Fetching metadata and daily values since {five_years_ago}...")

    with TradevilleClient() as client:
        for sym in all_symbols:
            if sym in symbols_seen:
                continue
            symbols_seen.add(sym)

            print(f"  [..] {sym:12s} fetching metadata and prices...", end=" ", flush=True)

            # 1. Fetch metadata
            metadata_res = client.get_symbol_price(sym)
            if "data" in metadata_res and not metadata_res.get("is_offline"):
                sdata = metadata_res["data"]
                name = sdata.get("Name", [sym])[0]
                shares_outstanding = sdata.get("SharesNr", [None])[0]
                isin = sdata.get("ISIN", [None])[0]
                earnings = sdata.get("Earnings", [None])[0]
                earn_date = sdata.get("EarnDate", [None])[0]
                price = sdata.get("Price", [0.0])[0]

                market_cap = None
                if shares_outstanding and price:
                    market_cap = shares_outstanding * price

                upsert_company(
                    conn, sym, name,
                    shares_outstanding=shares_outstanding,
                    market_cap=market_cap,
                    isin=isin,
                    earnings=earnings,
                    earn_date=earn_date
                )

            # 2. Fetch price history
            prices = client.get_daily_values(sym, start_date=five_years_ago)
            if prices:
                n = upsert_prices(conn, sym, prices)
                total_prices += n
                print(f"OK ({n} prices)")
            else:
                print("EMPTY")

            time.sleep(0.5)

    conn.commit()
    conn.close()
    print(f"\nDone. Total prices upserted: {total_prices}")

    # Recalculate metrics for all companies (market cap may have changed)
    print("\nRecalculating metrics...")
    from metrics_calculator import calculate_all
    calculate_all()
    print("\nMetrics updated.")

if __name__ == "__main__":
    main()
