#!/usr/bin/env python3
"""
Fetch company financial data (quarterly/annual reports, price history, key metrics)
from Yahoo Finance and save to company_data.json for the dashboard.
"""
import json
import os
import sys
from datetime import datetime, timezone

# Bootstrap to venv
VENV_PYTHON = "/opt/data/.venv/bin/python3"
if sys.executable != VENV_PYTHON:
    import subprocess
    result = subprocess.run([VENV_PYTHON, __file__] + sys.argv[1:])
    sys.exit(result.returncode)

import yfinance as yf

BASE_DIR = "/financial-dashboard"
PORTFOLIO_FILE = os.path.join(BASE_DIR, "bvb_portfolio.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "company_data.json")
YAHOO_SUFFIX = ".RO"


def yahoo_symbol(simbol):
    """Map BVB symbol to Yahoo Finance format."""
    if simbol.startswith("EBTLV"):
        return None
    return f"{simbol}{YAHOO_SUFFIX}"


def safe_val(val, default=None):
    """Return a safe value (handle NaN, Inf)."""
    if val is None:
        return default
    try:
        if isinstance(val, float) and (val != val or val == float('inf') or val == float('-inf')):
            return default
        return val
    except:
        return default


def fetch_company_data(simbol, nume):
    """Fetch all available financial data for a company."""
    ysym = yahoo_symbol(simbol)
    if ysym is None:
        return None

    result = {
        "simbol": simbol,
        "nume": nume,
        "error": None,
        "metrics": {},
        "quarterly": [],
        "annual": [],
        "price_history": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        ticker = yf.Ticker(ysym)
        info = ticker.info

        # --- Key metrics ---
        metrics_fields = [
            ("marketCap", "marketCap"),
            ("trailingPE", "trailingPE"),
            ("forwardPE", "forwardPE"),
            ("priceToBook", "priceToBook"),
            ("dividendYield", "dividendYield"),
            ("dividendRate", "dividendRate"),
            ("totalRevenue", "totalRevenue"),
            ("profitMargins", "profitMargins"),
            ("returnOnEquity", "returnOnEquity"),
            ("returnOnAssets", "returnOnAssets"),
            ("earningsGrowth", "earningsGrowth"),
            ("revenueGrowth", "revenueGrowth"),
            ("beta", "beta"),
            ("fiftyTwoWeekHigh", "fiftyTwoWeekHigh"),
            ("fiftyTwoWeekLow", "fiftyTwoWeekLow"),
            ("sector", "sector"),
            ("industry", "industry"),
            ("longBusinessSummary", "longBusinessSummary"),
            ("enterpriseValue", "enterpriseValue"),
            ("priceToSalesTrailing12Months", "priceToSalesTrailing12Months"),
            ("debtToEquity", "debtToEquity"),
            ("currentRatio", "currentRatio"),
            ("bookValue", "bookValue"),
            ("earningsQuarterlyGrowth", "earningsQuarterlyGrowth"),
            ("operatingMargins", "operatingMargins"),
            ("freeCashflow", "freeCashflow"),
            ("operatingCashflow", "operatingCashflow"),
        ]
        for key, field in metrics_fields:
            val = info.get(field)
            if val is not None:
                result["metrics"][key] = safe_val(val)

        # --- Quarterly financials ---
        try:
            qf = ticker.quarterly_financials
            if qf is not None and not qf.empty:
                for col in qf.columns:
                    quarter_data = {
                        "date": col.isoformat() if hasattr(col, 'isoformat') else str(col),
                        "items": {}
                    }
                    for row_name in ["Total Revenue", "Net Income", "EBITDA", "Operating Income",
                                     "Diluted EPS", "Basic EPS", "Gross Profit"]:
                        if row_name in qf.index:
                            val = qf.loc[row_name, col]
                            if val is not None and not (isinstance(val, float) and (val != val)):
                                quarter_data["items"][row_name] = round(float(val), 2) if val != int(val) else int(val)
                    # Ensure EPS exists - if Diluted EPS not present but Basic EPS is
                    if "Diluted EPS" not in quarter_data["items"] and "Basic EPS" in quarter_data["items"]:
                        quarter_data["items"]["Diluted EPS"] = quarter_data["items"]["Basic EPS"]
                    result["quarterly"].append(quarter_data)
        except Exception as e:
            pass

        # --- Annual financials ---
        try:
            af = ticker.financials
            if af is not None and not af.empty:
                for col in af.columns:
                    year_data = {
                        "date": col.isoformat() if hasattr(col, 'isoformat') else str(col),
                        "items": {}
                    }
                    for row_name in ["Total Revenue", "Net Income", "EBITDA", "Operating Income",
                                     "Diluted EPS", "Basic EPS", "Gross Profit", "Pretax Income",
                                     "Interest Expense", "Total Operating Expenses"]:
                        if row_name in af.index:
                            val = af.loc[row_name, col]
                            if val is not None and not (isinstance(val, float) and (val != val)):
                                year_data["items"][row_name] = round(float(val), 2) if val != int(val) else int(val)
                    result["annual"].append(year_data)
        except Exception as e:
            pass

        # --- Price history (1 year of daily closes) ---
        try:
            hist = ticker.history(period="1y")
            if hist is not None and not hist.empty:
                result["price_history"] = [
                    {
                        "date": d.isoformat() if hasattr(d, 'isoformat') else str(d),
                        "close": round(float(hist.loc[d, "Close"]), 4),
                        "volume": int(hist.loc[d, "Volume"]),
                    }
                    for d in hist.index
                ]
        except Exception as e:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    # Load portfolio to get symbols
    if not os.path.exists(PORTFOLIO_FILE):
        print(f"Portfolio file not found: {PORTFOLIO_FILE}")
        sys.exit(1)

    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        portfolio = json.load(f)

    # Fetch data for each holding that has a Yahoo symbol
    results = {}
    for h in portfolio["holdings"]:
        sym = h["simbol"]
        name = h["nume"]
        ysym = yahoo_symbol(sym)
        if ysym is None:
            print(f"  [--] {sym:12s} (no Yahoo symbol, skip)")
            continue
        print(f"  [..] {sym:12s} fetching financial data...", end=" ")
        sys.stdout.flush()
        data = fetch_company_data(sym, name)
        if data:
            # Count what we got
            q_count = len(data.get("quarterly", []))
            a_count = len(data.get("annual", []))
            p_count = len(data.get("price_history", []))
            m_count = len(data.get("metrics", {}))
            results[sym] = data
            err = data.get("error", "")
            if err:
                print(f"ERROR ({err[:50]})")
            else:
                print(f"OK ({m_count} metrics, {q_count}q, {a_count}a, {p_count} prices)")
        else:
            print("FAILED (empty)")
        # Rate limit courtesy
        import time
        time.sleep(0.5)

    # Save to file
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "companies": results,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(results)} companies to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
