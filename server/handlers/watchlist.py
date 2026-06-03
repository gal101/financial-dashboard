"""
Watchlist CRUD handler.
GET /watchlist — returns current watchlist JSON.
POST /watchlist — adds a symbol, triggers scraping if needed.
DELETE /watchlist?symbol=X — removes a symbol.
"""

import json
import logging
import os
import subprocess
import sys

from shared.config import (
    WATCHLIST_FILE, COMPANY_DATA_FILE, PENDING_SCRAPES_FILE,
    REQUIRED_METRICS, SCRAPE_RESULTS_DIR, BASE_DIR
)
from scraper.trigger import trigger_scraping

log = logging.getLogger("bvb-server")


def _fetch_price_for(symbol: str):
    """Run portfolio_updater.py (which generates watchlist_data.json AND calls company_fetcher.py)."""
    try:
        # portfolio_updater.py reads both bvb_portfolio.json + watchlist.json,
        # fetches prices for all symbols via yfinance, writes bvb_portfolio.json
        # AND watchlist_data.json (the file the dashboard fetches for watchlist prices).
        # At the end it also triggers company_fetcher.py for SQLite price_history.
        fetcher = os.path.join(BASE_DIR, "portfolio_updater.py")
        result = subprocess.run(
            [sys.executable, fetcher, "--force"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info(f"[price] {symbol} — price + watchlist fetch OK")
        else:
            log.warning(f"[price] {symbol} — fetch stderr: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        log.warning(f"[price] {symbol} — fetch timed out after 120s")
    except Exception as e:
        log.warning(f"[price] {symbol} — fetch error: {e}")


def handle_get_watchlist() -> dict:
    """Return current watchlist."""
    if not os.path.exists(WATCHLIST_FILE):
        return {"simbols": []}
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def handle_add_to_watchlist(body: dict) -> dict:
    """Add a symbol to watchlist. Trigger scraping if company data is sparse."""
    symbol = (body.get("symbol") or "").strip().upper()
    if not symbol:
        return {"success": False, "error": "Missing 'symbol' field"}

    # Read current watchlist
    wl = {"simbols": []}
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            wl = json.load(f)

    if symbol in wl.get("simbols", []):
        return {"success": False, "error": f"{symbol} already in watchlist"}

    wl["simbols"].append(symbol)

    # Write back
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

    # Add to active websocket subscriptions and subscribe
    streamer_active = False
    try:
        import server.server as server
        if server.streamer and server.streamer.authenticated:
            server.streamer.active_tickers.add(symbol)
            server.streamer._resubscribe()
            log.info(f"[watchlist] Added {symbol} to active websocket subscriptions")
            import threading
            threading.Thread(
                target=server.streamer._fetch_symbol_details,
                args=([symbol],),
                daemon=True
            ).start()
            streamer_active = True
    except Exception as e:
        log.warning(f"[watchlist] Could not update active subscriptions for {symbol}: {e}")
    if not streamer_active:
        log.info(f"[price] {symbol} — running offline price fetch fallback...")
        _fetch_price_for(symbol)
    else:
        log.info(f"[price] {symbol} — live price fetch triggered via WebSocket")

    # Check if company data is sparse — trigger scraping
    scraping_triggered = False
    need_scrape = _company_needs_scraping(symbol)
    if need_scrape:
        log.info(f"[scrape] {symbol} — data sparse, triggering scraping pipeline (needs: {need_scrape})")
        # Add to pending scrapes
        _add_pending_scrape(symbol, need_scrape)
        # Fire webhook
        ok = trigger_scraping(symbol)
        scraping_triggered = ok
        if ok:
            log.info(f"[scrape] {symbol} — webhook sent successfully to Hermes")
        else:
            log.error(f"[scrape] {symbol} — webhook FAILED")
    else:
        log.debug(f"[scrape] {symbol} — data complete, no scraping needed")

    return {
        "success": True,
        "watchlist": wl,
        "scraping_triggered": scraping_triggered
    }


def handle_delete_from_watchlist(symbol: str) -> dict:
    """Remove a symbol from watchlist."""
    symbol = symbol.strip().upper()
    if not symbol:
        return {"success": False, "error": "Missing symbol"}

    if not os.path.exists(WATCHLIST_FILE):
        return {"success": False, "error": "Watchlist not found"}

    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        wl = json.load(f)

    if symbol not in wl.get("simbols", []):
        return {"success": False, "error": f"{symbol} not in watchlist"}

    wl["simbols"] = [s for s in wl["simbols"] if s != symbol]

    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=2)

    # Remove from active websocket subscriptions if present
    try:
        import server
        if server.streamer and symbol in server.streamer.active_tickers:
            server.streamer.active_tickers.discard(symbol)
            log.info(f"[watchlist] Removed {symbol} from active websocket subscriptions")
    except Exception as e:
        log.warning(f"[watchlist] Could not update active subscriptions for {symbol}: {e}")
    # Also regenerate watchlist_data.json without the deleted symbol
    log.info(f"[price] {symbol} — regenerating watchlist prices after delete...")
    _fetch_price_for(symbol)

    return {"success": True, "watchlist": wl}


def _company_needs_scraping(symbol: str) -> list:
    """Check company_data.json for missing metrics. Returns list of missing metric names.
    Returns empty list if data is complete or company_data.json doesn't exist."""
    if not os.path.exists(COMPANY_DATA_FILE):
        log.info(f"[scrape] {symbol} — no company_data.json, all metrics needed")
        return REQUIRED_METRICS  # All needed, no file at all

    with open(COMPANY_DATA_FILE, "r", encoding="utf-8") as f:
        cd = json.load(f)

    comp = cd.get("companies", {}).get(symbol, {})
    metrics = comp.get("metrics", {})

    # If company doesn't exist at all in company_data, all metrics needed
    if not comp:
        log.info(f"[scrape] {symbol} — not found in company_data.json, all metrics needed")
        return REQUIRED_METRICS

    # Check which required metrics are missing (None or 0 or absent)
    missing = []
    for m in REQUIRED_METRICS:
        val = metrics.get(m)
        if val is None or val == 0:
            missing.append(m)

    # If more than 30% metrics are missing, trigger scraping
    pct_missing = len(missing) / len(REQUIRED_METRICS) * 100
    if len(missing) > len(REQUIRED_METRICS) * 0.3:
        log.info(f"[scrape] {symbol} — {len(missing)}/{len(REQUIRED_METRICS)} metrics missing ({pct_missing:.0f}%), triggering: {missing[:5]}{'...' if len(missing) > 5 else ''}")
        return missing

    log.debug(f"[scrape] {symbol} — {len(missing)}/{len(REQUIRED_METRICS)} metrics missing ({pct_missing:.0f}%), below threshold")
    return []


def _add_pending_scrape(symbol: str, metrics_needed: list):
    """Add a scrape task to pending_scrapes.json."""
    pending = {"tasks": []}
    if os.path.exists(PENDING_SCRAPES_FILE):
        with open(PENDING_SCRAPES_FILE, "r", encoding="utf-8") as f:
            pending = json.load(f)

    # Check if already pending for this symbol
    for task in pending.get("tasks", []):
        if task.get("symbol") == symbol and task.get("status") in ("pending", "needs_fix"):
            log.debug(f"[scrape] {symbol} — already in pending queue, skipping")
            return  # Already queued

    pending["tasks"].append({
        "symbol": symbol,
        "status": "pending",
        "metrics_needed": metrics_needed,
        "urls": [
            f"https://bvb.ro/infocont/infocont.php?simbol={symbol}"
        ],
        "errors": None
    })

    os.makedirs(os.path.dirname(PENDING_SCRAPES_FILE), exist_ok=True)
    with open(PENDING_SCRAPES_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    log.info(f"[scrape] {symbol} — added to pending queue ({len(pending['tasks'])} total)")
