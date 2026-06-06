"""
POST /refresh handler.
Runs portfolio_updater.py to fetch live prices, then returns updated JSON.
Also updates watchlist prices.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from shared.config import (
    PYTHON_BIN, VENV_PYTHON, UPDATER_SCRIPT, PORTFOLIO_FILE,
    WATCHLIST_FILE, WATCHLIST_DATA_FILE
)

# Pick the right Python binary
import os as _os
python_bin = PYTHON_BIN if _os.path.exists(PYTHON_BIN) else VENV_PYTHON


def handle_refresh() -> dict:
    """Run the updater and return fresh data."""
    result = {"success": False, "data": None, "watchlist_data": None, "error": None}

    # 1. Run portfolio_updater.py
    try:
        proc = subprocess.run(
            [python_bin, UPDATER_SCRIPT],
            capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            result["error"] = f"Updater failed (exit {proc.returncode}): {proc.stderr[:500]}"
            return result
    except subprocess.TimeoutExpired:
        result["error"] = "Updater timed out (120s)"
        return result
    except Exception as e:
        result["error"] = f"Failed to run updater: {e}"
        return result

    # 2. Read updated portfolio
    try:
        from handlers.portfolio import handle_get_portfolio
        result["data"] = handle_get_portfolio()
    except Exception as e:
        result["error"] = f"Failed to get portfolio after update: {e}"
        return result

    # 3. Update watchlist prices (server-side Yahoo fetch for watchlist symbols)
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                wl = json.load(f)
            wl_syms = wl.get("simbols", [])

            if wl_syms:
                wl_prices = _fetch_watchlist_prices(wl_syms)
                os.makedirs(os.path.dirname(WATCHLIST_DATA_FILE), exist_ok=True)
                with open(WATCHLIST_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(wl_prices, f, ensure_ascii=False, indent=2)
                result["watchlist_data"] = wl_prices
        except Exception as e:
            result["error"] = (result["error"] or "") + f"; watchlist: {e}"

    result["success"] = True
    return result


def _fetch_watchlist_prices(symbols: list) -> dict:
    """Fetch prices for watchlist symbols using yfinance server-side (no CORS)."""
    result = {"updated_at": datetime.now(timezone.utc).isoformat(), "prices": {}}

    # Use yfinance directly
    try:
        import yfinance as yf
    except ImportError:
        # Use venv python inline
        code = f"""
import json, yfinance as yf
syms = {json.dumps(symbols)}
result = {{}}
for s in syms:
    try:
        t = yf.Ticker(s + '.RO')
        info = t.info
        p = info.get('regularMarketPrice')
        prev = info.get('regularMarketPreviousClose')
        if p:
            chg = ((p - prev) / prev * 100) if prev and prev > 0 else 0
            result[s] = {{'price': round(p, 4), 'changePct': round(chg, 2)}}
        else:
            result[s] = None
    except:
        result[s] = None
print(json.dumps(result, ensure_ascii=False))
"""
        proc = subprocess.run(
            [python_bin, "-c", code],
            capture_output=True, text=True, timeout=30
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result["prices"] = json.loads(proc.stdout.strip())
        return result

    # If yfinance is importable directly (same venv path)
    for s in symbols:
        try:
            t = yf.Ticker(s + ".RO")
            info = t.info
            p = info.get("regularMarketPrice")
            prev = info.get("regularMarketPreviousClose")
            if p:
                chg = ((p - prev) / prev * 100) if prev and prev > 0 else 0
                result["prices"][s] = {"price": round(p, 4), "changePct": round(chg, 2)}
            else:
                result["prices"][s] = None
        except Exception:
            result["prices"][s] = None

    return result
