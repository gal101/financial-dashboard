#!/usr/bin/env python3
"""
Fetch daily price history from Yahoo Finance and write to SQLite.

GREEN ZONE ONLY: this script ONLY touches the price_history table.
All other tables (companies, quarterly, annual, bvc, calendar,
calculated_metrics) are READ-ONLY for this script.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

# Bootstrap to venv
VENV_PYTHON = "/opt/data/.venv/bin/python3"
if sys.executable != VENV_PYTHON:
    import subprocess
    result = subprocess.run([VENV_PYTHON, __file__] + sys.argv[1:])
    sys.exit(result.returncode)

import yfinance as yf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import get_db, upsert_prices, sanitize_val

PORTFOLIO_FILE = os.path.join(SCRIPT_DIR, "bvb_portfolio.json")
WATCHLIST_FILE = os.path.join(SCRIPT_DIR, "watchlist.json")
YAHOO_SUFFIX = ".RO"


def yahoo_symbol(simbol):
    if simbol.startswith("EBTLV"):
        return None
    return f"{simbol}{YAHOO_SUFFIX}"


def fetch_prices(simbol):
    """Fetch 5-year daily price history from Yahoo."""
    ysym = yahoo_symbol(simbol)
    if ysym is None:
        return []

    ticker = yf.Ticker(ysym)
    hist = ticker.history(period="5y")
    if hist is None or hist.empty:
        return []

    prices = []
    for d in hist.index:
        close = float(hist.loc[d, "Close"])
        close = sanitize_val(close)
        if close is None:
            continue
        prices.append({
            "date": d.isoformat() if hasattr(d, 'isoformat') else str(d),
            "close": round(close, 4),
        })
    return prices


def main():
    conn = get_db()
    symbols_seen = set()
    total_prices = 0

    # 1. Portfolio symbols
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            portfolio = json.load(f)
        for h in portfolio["holdings"]:
            sym = h["simbol"]
            symbols_seen.add(sym)
            ysym = yahoo_symbol(sym)
            if ysym is None:
                print(f"  [--] {sym:12s} (no Yahoo symbol, skip)")
                continue
            print(f"  [..] {sym:12s} fetching prices...", end=" ", flush=True)
            prices = fetch_prices(sym)
            if prices:
                n = upsert_prices(conn, sym, prices)
                total_prices += n
                print(f"OK ({n} prices)")
            else:
                print("EMPTY")
            time.sleep(0.5)

    # 2. Watchlist symbols (not already in portfolio)
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            wl = json.load(f)
        for sym in wl.get("simbols", []):
            if sym in symbols_seen:
                continue
            symbols_seen.add(sym)
            ysym = yahoo_symbol(sym)
            if ysym is None:
                print(f"  [--] {sym:12s} (no Yahoo symbol, skip)")
                continue
            print(f"  [..] {sym:12s} fetching prices...", end=" ", flush=True)
            prices = fetch_prices(sym)
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
