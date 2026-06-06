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
sys.path.insert(0, SCRIPT_DIR)
from db import get_db, upsert_prices, upsert_company, sanitize_val
from shared.tradeville_client import TradevilleClient
from shared.config import WATCHLIST_FILE
from db import get_db, get_user_db

def _extract_scalar(val, default=None):
    """Extract a scalar from a Tradeville columnar value (which can be list, dict, or scalar)."""
    if val is None:
        return default
    if isinstance(val, list):
        if len(val) == 0:
            return default
        inner = val[0]
        if isinstance(inner, dict):
            return default
        return inner
    if isinstance(val, dict):
        return default
    return val

def main():
    conn = get_db()
    symbols_seen = set()
    total_prices = 0

    # Parse targeted tickers
    target_tickers = [arg.upper() for arg in sys.argv[1:] if not arg.startswith("--")]

    # Load portfolio symbols
    portfolio_symbols = []
    user_conn = get_user_db()
    try:
        rows = user_conn.execute("SELECT symbol FROM portfolio_holdings").fetchall()
        portfolio_symbols = [r["symbol"] for r in rows]
    except Exception as e:
        print(f"Error loading portfolio symbols: {e}")
    finally:
        user_conn.close()

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
                name = _extract_scalar(sdata.get("Name"), sym)
                shares_outstanding = _extract_scalar(sdata.get("SharesNr"))
                isin = _extract_scalar(sdata.get("ISIN"))
                earnings = _extract_scalar(sdata.get("Earnings"))
                earn_date = _extract_scalar(sdata.get("EarnDate"))
                price = _extract_scalar(sdata.get("Price"), 0.0)
                dividend = _extract_scalar(sdata.get("Dividend"))
                div_price = _extract_scalar(sdata.get("DivPrice"))
                ref_price = _extract_scalar(sdata.get("RefPrice"))

                market_cap = None
                if shares_outstanding and price:
                    try:
                        market_cap = int(shares_outstanding) * float(price)
                    except (ValueError, TypeError):
                        pass

                upsert_company(
                    conn, sym, name,
                    shares_outstanding=shares_outstanding,
                    market_cap=market_cap,
                    isin=isin,
                    earnings=earnings,
                    earn_date=earn_date,
                    dividend=dividend,
                    div_price=div_price,
                    ref_price=ref_price
                )
                conn.commit()

            # 2. Fetch price history (incremental)
            start_dt = five_years_ago
            max_date_str = None
            try:
                row = conn.execute(
                    "SELECT MAX(date) as max_date FROM price_history WHERE symbol = ?",
                    (sym,)
                ).fetchone()
                if row and row["max_date"]:
                    max_date_str = row["max_date"]
                    max_date = datetime.strptime(max_date_str, "%Y-%m-%d").date()
                    start_dt = max_date + timedelta(days=1)
            except Exception as e:
                print(f"(db error: {e})", end=" ")
                start_dt = five_years_ago
            if start_dt > date.today():
                print(f"UP-TO-DATE (max date: {max_date_str})")
                continue
            prices = client.get_daily_values(sym, start_date=start_dt)
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

    # Regenerate company_data.json with newly fetched data
    from db import export_to_json
    print("Regenerating company_data.json...")
    export_to_json()
    print("Done.")

if __name__ == "__main__":
    import time
    start_time = time.time()
    try:
        from shared.tradeville_client import TradevilleClient
        with TradevilleClient() as client:
            client.ping_task("Actualizare Date Istorice", "running")
    except Exception:
        pass
    try:
        main()
        duration = round(time.time() - start_time, 2)
        try:
            with TradevilleClient() as client:
                client.ping_task("Actualizare Date Istorice", "success", duration=duration)
        except Exception:
            pass
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        try:
            with TradevilleClient() as client:
                client.ping_task("Actualizare Date Istorice", "failed", error=str(e), duration=duration)
        except Exception:
            pass
        raise e
