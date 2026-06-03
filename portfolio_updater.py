#!/usr/bin/env python3
"""
BVB Portfolio Price Updater
============================
Updates portfolio holdings and watchlist prices using Tradeville API.
Automatically syncs portfolio from Tradeville when online with a real account.

Usage:
    python3 portfolio_updater.py          # normal (skips weekends)
    python3 portfolio_updater.py --force  # force even on weekends
    python3 portfolio_updater.py --dry-run
    python3 portfolio_updater.py TLV SNP  # targeted update for TLV and SNP
"""

import json
import os
import sys
from datetime import datetime, timezone

# Bootstrap: ensure virtual environment is used if present in Hermes container
VENV_PYTHON = "/opt/data/.venv/bin/python3"
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    import subprocess
    result = subprocess.run([VENV_PYTHON, __file__] + sys.argv[1:])
    sys.exit(result.returncode)

# Add server directory to path to import Tradeville client
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "server"))

from shared.tradeville_client import TradevilleClient

JSON_FILE = os.path.join(BASE_DIR, "bvb_portfolio.json")
WATCHLIST_FILE = os.path.join(BASE_DIR, "watchlist.json")
WATCHLIST_DATA_FILE = os.path.join(BASE_DIR, "watchlist_data.json")

def fetch_price(client, simbol):
    """Fetch current price and reference price from Tradeville API, calculate change."""
    try:
        res = client.get_symbol_price(simbol)
        data = res.get("data")
        if not data or not isinstance(data, dict):
            return None
            
        prices = data.get("Price")
        ref_prices = data.get("RefPrice")
        
        if not prices or len(prices) == 0:
            return None
            
        price = float(prices[0])
        ref_price = float(ref_prices[0]) if ref_prices and len(ref_prices) > 0 else price
        
        if ref_price > 0:
            change_pct = ((price - ref_price) / ref_price) * 100
        else:
            change_pct = 0.0
            
        leverages = data.get("Leverage")
        barriers = data.get("Barrier")
        is_structured = False
        if leverages and len(leverages) > 0 and leverages[0] is not None:
            is_structured = True
        if barriers and len(barriers) > 0 and barriers[0] is not None:
            is_structured = True
        return {
            "price": round(price, 4),
            "change_pct": round(change_pct, 2),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "is_structured": is_structured
        }
    except Exception as e:
        print(f"  ! Error fetching Tradeville price for {simbol}: {e}")
        return None

def is_weekday():
    """Check if today is a weekday in EEST (UTC+2)."""
    now = datetime.now(timezone.utc)
    return now.weekday() < 5, (now.hour + 2) % 24, now

def load_portfolio():
    if not os.path.exists(JSON_FILE):
        # Fallback to example
        example = os.path.join(BASE_DIR, "bvb_portfolio.example.json")
        if os.path.exists(example):
            with open(example, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"metadata": {"total_investit_RON": 0}, "holdings": []}
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_watchlist():
    """Load watchlist symbols. Returns empty list if file missing."""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("simbols", [])

def save_portfolio(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def print_summary(portfolio):
    m = portfolio["metadata"]
    print("-" * 50)
    print(f"Portofoliu: {m.get('sursa', 'Necunoscut')}")
    print(f"Total Investit: {m.get('total_investit_RON', 0):>12.2f} RON")
    print(f"Evaluare Curenta: {m.get('total_evaluare_RON', 0):>10.2f} RON")
    profit = m.get('total_profit_pierdere_RON', 0)
    pct = m.get('return_total_pct', 0)
    sign = "+" if profit >= 0 else ""
    print(f"Profit/Pierdere: {sign}{profit:>11.2f} RON ({sign}{pct:.2f}%)")
    print("-" * 50)
    print()

def main():
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    weekday, eest_hour, now = is_weekday()

    if not weekday and not force:
        print(f"Weekend (EEST {eest_hour:02d}:{now.minute:02d}) -- piata inchisa. --force pentru a forta.")
        sys.exit(0)

    # Parse targeted symbols if any (non-flag arguments)
    target_tickers = [arg.upper() for arg in sys.argv[1:] if not arg.startswith("--")]

    print(f"Actualizare preturi BVB -- {now.strftime('%Y-%m-%d %H:%M:%S')} UTC  (EEST {eest_hour:02d}:{now.minute:02d})")
    if target_tickers:
        print(f"Targeted symbols: {', '.join(target_tickers)}")
    print()

    portfolio = load_portfolio()
    
    with TradevilleClient() as client:
        # 1. Automated Portfolio Sync
        portfolio_res = client.send_request({"cmd": "Portfolio", "prm": {"data": None}})
        # Check if real account and online (demo accounts start with !)
        is_real_account = False
        if "data" in portfolio_res and not portfolio_res.get("is_offline"):
            accounts = portfolio_res["data"].get("Account", [])
            if accounts and not any(acc.startswith("!") for acc in accounts):
                is_real_account = True
                
        if is_real_account and not dry_run:
            print("Online Tradeville Portfolio sync starting...")
            data = portfolio_res["data"]
            symbols = data.get("Symbol", [])
            quantities = data.get("Quantity", [])
            avg_prices = data.get("AvgPrice", [])
            ptypes = data.get("PType", [])
            
            new_holdings = []
            for i in range(len(symbols)):
                sym = symbols[i]
                qty = quantities[i]
                avg_price = avg_prices[i]
                
                # Ignore cash or zero quantities
                if qty <= 0 or sym == "RON":
                    continue
                    
                tip = "actiuni"
                if i < len(ptypes) and ptypes[i] != "A":
                    tip = "struct"
                    
                # Find friendly name from existing holdings
                nume = sym
                for h in portfolio.get("holdings", []):
                    if h["simbol"] == sym:
                        nume = h["nume"]
                        break
                        
                new_holdings.append({
                    "simbol": sym,
                    "nume": nume,
                    "tip": tip,
                    "actiuni": qty,
                    "pret_medie_achizitie_RON": round(avg_price, 4),
                    "pret_actual_RON": 0.0,
                    "valoare_evaluata_RON": 0.0,
                    "profit_pierdere_RON": 0.0,
                    "investitie_initiala_RON": round(qty * avg_price, 2),
                    "variatie_pret_pct": 0.0,
                    "pondere_portofoliu_pct": 0.0
                })
            
            portfolio["holdings"] = new_holdings
            portfolio["metadata"]["sursa"] = "Tradeville API Live Sync"
            portfolio["metadata"]["valuta"] = "RON"
            portfolio["metadata"]["total_investit_RON"] = round(sum(h["investitie_initiala_RON"] for h in new_holdings), 2)
            portfolio["metadata"]["numar_pozitii"] = len(new_holdings)
            print(f"Synced {len(new_holdings)} holdings from Tradeville account.")
            
        portfolio_symbols = [h["simbol"] for h in portfolio["holdings"]]
        watchlist_symbols = load_watchlist()
        
        # Filter if targeted
        if target_tickers:
            all_symbols = [sym for sym in target_tickers if sym in portfolio_symbols or sym in watchlist_symbols]
        else:
            all_symbols = list(dict.fromkeys(portfolio_symbols + watchlist_symbols))
            
        prices = {}
        for sym in all_symbols:
            result = fetch_price(client, sym)
            if result:
                prices[sym] = result
                print(f"  [OK] {sym:12s} {result['price']:>10.4f} RON  ({result['change_pct']:+.2f}%)")
            else:
                print(f"  [--] {sym:12s} (fara date Tradeville, pastreaza referinta)")

        if dry_run:
            print("\nDry run -- nimic modificat.")
            sys.exit(0)

        # Update holdings in portfolio
        updated = 0
        for h in portfolio["holdings"]:
            sym = h["simbol"]
            if target_tickers and sym not in target_tickers:
                continue
            if sym in prices:
                p = prices[sym]
                h["pret_actual_RON"] = p["price"]
                h["variatie_pret_pct"] = p["change_pct"]
                h["tip"] = "struct" if p.get("is_structured") else "actiuni"
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
        if m.get("total_investit_RON", 0) > 0:
            m["return_total_pct"] = round(
                m["total_profit_pierdere_RON"] / m["total_investit_RON"] * 100, 2
            )
        else:
            m["return_total_pct"] = 0.0
        m["last_price_update"] = datetime.now(timezone.utc).isoformat()

        save_portfolio(portfolio)
        
        # Write watchlist prices
        if watchlist_symbols:
            wl_prices = {}
            for sym in watchlist_symbols:
                if target_tickers and sym not in target_tickers:
                    # Keep old watchlist price if not targeted
                    continue
                if sym in prices:
                    p = prices[sym]
                    wl_prices[sym] = {
                        "price": p["price"],
                        "changePct": p["change_pct"] / 100,
                    }
                    
            # If targeted, load existing watchlist data to merge
            if target_tickers and os.path.exists(WATCHLIST_DATA_FILE):
                try:
                    with open(WATCHLIST_DATA_FILE, "r", encoding="utf-8") as f:
                        old_wl = json.load(f)
                    # merge
                    for k, v in old_wl.get("prices", {}).items():
                        if k not in wl_prices:
                            wl_prices[k] = v
                except Exception:
                    pass
                    
            wl_data = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "prices": wl_prices,
            }
            with open(WATCHLIST_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(wl_data, f, ensure_ascii=False, indent=2)
            print(f"  Watchlist salvat: {len(wl_prices)} simboluri")
        
        print_summary(portfolio)
        print(f"  Preturi actualizate: {updated}/{len(all_symbols)}")

    # Also refresh company financial data
    print("\nActualizare si date financiare...")
    import subprocess
    subprocess.run([sys.executable, os.path.join(BASE_DIR, "company_fetcher.py")] + target_tickers)
    print("Gata!")

if __name__ == "__main__":
    import time
    start_time = time.time()
    try:
        with TradevilleClient() as client:
            client.ping_task("Actualizare Portofoliu", "running")
    except Exception:
        pass
    try:
        main()
        duration = round(time.time() - start_time, 2)
        try:
            with TradevilleClient() as client:
                client.ping_task("Actualizare Portofoliu", "success", duration=duration)
        except Exception:
            pass
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        try:
            with TradevilleClient() as client:
                client.ping_task("Actualizare Portofoliu", "failed", error=str(e), duration=duration)
        except Exception:
            pass
        raise e
