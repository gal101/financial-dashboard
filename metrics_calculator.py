#!/usr/bin/env python3
"""
Calculate financial metrics from SQLite data and write to calculated_metrics.

Trailing P/E, Forward P/E, EPS, profit margin, etc.
Uses: quarterly data (TTM), BVC (forward), shares outstanding, current price.

Run after ANY data import (scrape callback, price update).
"""
import json, os, sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import get_db, get_company, upsert_metrics, sanitize_val


def get_market_cap(conn, symbol):
    """Get latest market cap from Yahoo info or calculate from price * shares."""
    # Try company_data.json first (Yahoo marketCap)
    cd_path = os.path.join(SCRIPT_DIR, "company_data.json")
    if os.path.exists(cd_path):
        with open(cd_path) as f:
            cd = json.load(f)
        comp = cd.get("companies", {}).get(symbol, {})
        m = comp.get("metrics", {})
        mc = m.get("marketCap")
        if mc:
            return float(mc)

    # Fallback: price * shares
    comp = get_company(conn, symbol)
    if not comp:
        return None
    shares = comp.get("shares_outstanding")
    if not shares:
        return None

    # Get latest price from price_history
    prices = comp.get("price_history", [])
    if prices:
        last = prices[-1]["close"]
        return last * shares

    return None


def calc_ttm(quarterly):
    """Calculate TTM (trailing 12 months) from last 4 quarterly entries.
    Quarterly entries should be in chronological order (oldest first).
    Takes the last 4 entries."""
    if not quarterly or len(quarterly) < 4:
        return None, None

    # Last 4 quarters (entries are sorted oldest-first, so take the last 4)
    last4 = quarterly[-4:]
    ttm_rev = sum(q.get("revenue") or 0 for q in last4)
    ttm_ni = sum(q.get("net_income") or 0 for q in last4)
    return ttm_rev, ttm_ni


def calc_metrics(conn, symbol):
    """Calculate all metrics for a symbol and upsert into calculated_metrics."""
    comp = get_company(conn, symbol)
    if not comp:
        return {}

    shares = comp.get("shares_outstanding")
    quarterly = comp.get("quarterly", [])
    bvc = comp.get("bvc")
    market_cap = get_market_cap(conn, symbol)

    ttm_rev, ttm_ni = calc_ttm(quarterly)

    metrics = {}

    # EPS
    if ttm_ni is not None and shares:
        metrics["eps"] = sanitize_val(round(ttm_ni / shares, 6))

    # Trailing P/E
    if market_cap and ttm_ni and ttm_ni != 0:
        metrics["trailing_pe"] = sanitize_val(round(market_cap / ttm_ni, 2))

    # Forward P/E (from BVC)
    if market_cap and bvc and bvc.get("net_income") and bvc["net_income"] != 0:
        metrics["forward_pe"] = sanitize_val(round(market_cap / bvc["net_income"], 2))

    # Profit margin
    if ttm_ni is not None and ttm_rev and ttm_rev != 0:
        metrics["profit_margin"] = sanitize_val(round(ttm_ni / ttm_rev, 4))

    # TTM net income (stored for frontend EPS calc)
    if ttm_ni is not None:
        metrics["ttm_net_income"] = sanitize_val(round(ttm_ni, 2))

    if metrics:
        upsert_metrics(conn, symbol, metrics)

    return metrics


def calculate_all():
    """Calculate metrics for ALL companies in the database."""
    conn = get_db()
    comps = conn.execute("SELECT symbol FROM companies").fetchall()
    results = {}
    for row in comps:
        sym = row["symbol"]
        m = calc_metrics(conn, sym)
        results[sym] = m
        if m:
            print(f"  {sym:12s} trailingPE={m.get('trailing_pe', '-')}  EPS={m.get('eps', '-')}  fwdPE={m.get('forward_pe', '-')}")
    conn.commit()
    conn.close()
    print(f"\nDone. {len(results)} companies processed.")
    return results


def calculate_one(symbol):
    """Calculate metrics for a single symbol."""
    conn = get_db()
    m = calc_metrics(conn, symbol)
    conn.commit()
    conn.close()
    if m:
        print(f"{symbol}: trailingPE={m.get('trailing_pe')} EPS={m.get('eps')} forwardPE={m.get('forward_pe')} profitMargin={m.get('profit_margin')}")
    else:
        print(f"{symbol}: no metrics calculated (missing data)")
    return m


if __name__ == "__main__":
    if len(sys.argv) > 1:
        calculate_one(sys.argv[1].upper())
    else:
        calculate_all()
