#!/usr/bin/env python3
"""BVB Dashboard Server — HTTP API server with logging."""
import json, os, sys, logging
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

_server_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.dirname(_server_dir))

from shared.config import SERVER_HOST, SERVER_PORT, COMPANY_DATA_FILE, PENDING_SCRAPES_FILE, SCRAPE_RESULTS_DIR
from handlers.refresh import handle_refresh
from handlers.watchlist import handle_get_watchlist, handle_add_to_watchlist, handle_delete_from_watchlist
from json_sanitizer import safe_json_dumps
from db import get_db, get_company, list_companies, backup as db_backup
from db import upsert_company, upsert_quarterly, upsert_annual, upsert_metrics, export_to_json

streamer = None

def get_offline_fallback(cmd: str, symbol: str) -> dict:
    import sqlite3
    from db import get_db
    
    if cmd == "Symbol" and symbol:
        conn = get_db()
        try:
            row = conn.execute("SELECT name, shares_outstanding FROM companies WHERE symbol = ?", (symbol,)).fetchone()
            price_row = conn.execute("SELECT close FROM price_history WHERE symbol = ? ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
            price = price_row["close"] if price_row else 0.0
            name = row["name"] if row else symbol
            shares = row["shares_outstanding"] if row else 0
            return {
                "cmd": "Symbol",
                "data": {
                    "Symbol": [symbol],
                    "Price": [price],
                    "RefPrice": [price],
                    "Bid": [price],
                    "Ask": [price],
                    "SharesNr": [shares],
                    "Name": [name]
                },
                "is_offline": True
            }
        except Exception as e:
            log.error(f"[fallback] Symbol offline fallback failed: {e}")
        finally:
            conn.close()
            
    elif cmd == "DailyValues" and symbol:
        conn = get_db()
        try:
            prices = conn.execute("SELECT date, open, high, low, close, volume FROM price_history WHERE symbol = ? ORDER BY date", (symbol,)).fetchall()
            dates = [p["date"] for p in prices]
            opens = [p["open"] if p["open"] is not None else p["close"] for p in prices]
            closes = [p["close"] for p in prices]
            highs = [p["high"] if p["high"] is not None else p["close"] for p in prices]
            lows = [p["low"] if p["low"] is not None else p["close"] for p in prices]
            volumes = [p["volume"] if p["volume"] is not None else 0 for p in prices]
            return {
                "cmd": "DailyValues",
                "data": {
                    "Symbol": [symbol] * len(prices),
                    "Date": dates,
                    "Open": opens,
                    "High": highs,
                    "Low": lows,
                    "Close": closes,
                    "Volume": volumes
                },
                "is_offline": True
            }
        except Exception as e:
            log.error(f"[fallback] DailyValues offline fallback failed: {e}")
        finally:
            conn.close()
            
    elif cmd == "Portfolio":
        import os, json
        pf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bvb_portfolio.json")
        symbols = []
        quantities = []
        avg_prices = []
        market_prices = []
        ptypes = []
        ccys = []
        accounts = []
        if os.path.exists(pf_path):
            try:
                with open(pf_path) as f:
                    pf_data = json.load(f)
                for h in pf_data.get("holdings", []):
                    symbols.append(h["simbol"])
                    quantities.append(h["actiuni"])
                    avg_prices.append(h["pret_medie_achizitie_RON"])
                    market_prices.append(h["pret_actual_RON"])
                    ptypes.append("A" if h.get("tip") == "actiuni" else "B")
                    ccys.append("RON")
                    accounts.append("!OFFLINE")
            except Exception as e:
                log.error(f"[fallback] Portfolio offline fallback failed: {e}")
        return {
            "cmd": "Portfolio",
            "data": {
                "Account": accounts,
                "Symbol": symbols,
                "Quantity": quantities,
                "AvgPrice": avg_prices,
                "MarketPrice": market_prices,
                "PType": ptypes,
                "Ccy": ccys
            },
            "is_offline": True
        }
        
    return {
        "cmd": cmd,
        "data": {},
        "is_offline": True,
        "error": "offline"
    }

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(_server_dir), "server.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bvb-server")

# ── HTTP Handler ─────────────────────────────────────────────────────────────

class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler with CORS, JSON responses, and logging."""

    def _send_json(self, data: dict, status: int = 200):
        body = safe_json_dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def log_message(self, format, *args):
        log.info(f"[http] {args[0]}")

    # ── CORS preflight ──────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET ─────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"status": "ok", "uptime": "running"})

        elif path == "/watchlist":
            data = handle_get_watchlist()
            self._send_json(data)

        elif path == "/company":
            symbol = params.get("symbol", [""])[0].strip().upper()
            log.info(f"[api] GET /company?symbol={symbol}")
            conn = get_db()
            try:
                if symbol:
                    comp = get_company(conn, symbol)
                    if comp:
                        log.debug(f"[api] company/{symbol} returned — {len(comp.get('quarterly',[]))}Q, {len(comp.get('annual',[]))}Y")
                        self._send_json(comp)
                    else:
                        log.warning(f"[api] company/{symbol} — NOT FOUND")
                        self._send_json({"error": f"Company not found: {symbol}"}, 404)
                else:
                    symbols = list_companies(conn)
                    self._send_json({"companies": symbols})
            finally:
                conn.close()

        elif path == "/companies":
            conn = get_db()
            try:
                symbols = list_companies(conn)
                self._send_json({"companies": symbols})
            finally:
                conn.close()

        elif path == "/transactions":
            log.info("[api] GET /transactions")
            conn = get_db()
            try:
                rows = conn.execute("SELECT * FROM user_transactions ORDER BY date DESC").fetchall()
                self._send_json({"transactions": [dict(r) for r in rows]})
            finally:
                conn.close()
        else:
            self._send_json({"error": "Not found"}, 404)

    # ── POST ────────────────────────────────────────────────────
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self._read_body()

        if path == "/refresh":
            log.info("[api] POST /refresh — starting...")
            result = handle_refresh()
            status = 200 if result["success"] else 500
            log.info(f"[api] POST /refresh → {'OK' if result['success'] else 'FAIL'}")
            self._send_json(result, status)

        elif path == "/watchlist":
            symbol = body.get("symbol", "?")
            log.info(f"[api] POST /watchlist add={symbol}")
            result = handle_add_to_watchlist(body)
            status = 200 if result["success"] else 400
            if result.get("scraping_triggered"):
                log.info(f"[api] watchlist/{symbol} — scraping triggered")
            self._send_json(result, status)

        elif path == "/scrape-callback":
            symbol = body.get("symbol", "?")
            log.info(f"[scrape] CALLBACK received for {symbol}")
            handled = _handle_scrape_callback(body)
            if handled["success"]:
                log.info(f"[scrape] CALLBACK {symbol} — MERGED successfully")
            else:
                log.warning(f"[scrape] CALLBACK {symbol} — REJECTED: {handled.get('error')} — {handled.get('details')}")
            self._send_json(handled)

        elif path == "/api/tradeville/request":
            cmd = body.get("cmd")
            prm = body.get("prm") or {}
            symbol = prm.get("symbol")
            if not symbol and prm.get("search"):
                symbol = prm.get("search")
                
            key = (cmd, symbol)
            
            import threading
            event = threading.Event()
            
            global streamer
            if streamer is None:
                log.error("[api] TradevilleStreamer is not initialized.")
                self._send_json({"error": "streamer_uninitialized"}, 500)
                return
                
            if not streamer.authenticated:
                log.info(f"[api] Streamer not authenticated. Returning offline fallback for {cmd} immediately.")
                fallback = get_offline_fallback(cmd, symbol)
                self._send_json(fallback)
                return
            req = {"event": event, "response": None}
            streamer.pending_requests[key] = req
            streamer.out_queue.put(body)
            
            completed = event.wait(timeout=10)
            
            # Pop the request safely
            streamer.pending_requests.pop(key, None)
            
            if completed and req["response"] is not None:
                self._send_json(req["response"])
            else:
                fallback = get_offline_fallback(cmd, symbol)
                self._send_json(fallback)
        else:
            self._send_json({"error": "Not found"}, 404)

    # ── DELETE ──────────────────────────────────────────────────
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/watchlist":
            symbol = params.get("symbol", [""])[0]
            log.info(f"[api] DELETE /watchlist symbol={symbol}")
            result = handle_delete_from_watchlist(symbol)
            status = 200 if result["success"] else 400
            self._send_json(result, status)
        else:
            self._send_json({"error": "Not found"}, 404)


# ── Scrape callback handlers ─────────────────────────────────────────────────

def _handle_scrape_callback(body: dict) -> dict:
    """Validate scraping results and merge into SQLite."""
    symbol = body.get("symbol", "").strip().upper()
    status = body.get("status", "")
    result_file = body.get("file", "")

    if not symbol or not result_file:
        log.error(f"[scrape] Missing symbol or file in callback: {body}")
        return {"success": False, "error": "Missing symbol or file"}

    full_path = os.path.join("/financial-dashboard", result_file)
    if not os.path.exists(full_path):
        log.error(f"[scrape] Result file not found: {full_path}")
        return {"success": False, "error": f"Result file not found: {full_path}"}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            scrape_data = json.load(f)
        log.debug(f"[scrape] {symbol} — file loaded: {len(scrape_data.get('quarterly',[]))}Q, {len(scrape_data.get('annual',[]))}Y, metrics={list(scrape_data.get('metrics',{}).keys())}")
    except Exception as e:
        log.error(f"[scrape] Failed to read result for {symbol}: {e}")
        return {"success": False, "error": f"Failed to read result: {e}"}

    errors = _validate_scrape_result(scrape_data)
    if errors:
        err_path = os.path.join(SCRAPE_RESULTS_DIR, f"{symbol}.errors.txt")
        os.makedirs(SCRAPE_RESULTS_DIR, exist_ok=True)
        with open(err_path, "w") as f:
            f.write("\n".join(errors))
        log.warning(f"[scrape] {symbol} validation FAILED: {errors}")
        _update_pending_status(symbol, "needs_fix")
        return {"success": False, "error": "Validation failed", "details": errors, "needs_fix": True}

    _merge_to_sqlite(symbol, scrape_data)
    log.info(f"[scrape] {symbol} — merged into SQLite, regenerating JSON...")
    
    export_to_json(COMPANY_DATA_FILE)
    log.info(f"[scrape] {symbol} — company_data.json regenerated")
    
    _remove_pending_task(symbol)
    return {"success": True, "symbol": symbol, "merged": True}


def _validate_scrape_result(data: dict) -> list:
    """Validate scraped data structure."""
    errors = []
    if "symbol" not in data:
        errors.append("Missing 'symbol' field")
    if "quarterly" not in data or not isinstance(data.get("quarterly"), list):
        errors.append("Missing or invalid 'quarterly' array")
    if "annual" not in data or not isinstance(data.get("annual"), list):
        errors.append("Missing or invalid 'annual' array")
    
    # Metrics are optional — quarterly + annual are the minimum
    # (changed from requiring non-empty metrics)
    if "scraped_at" not in data:
        errors.append("Missing 'scraped_at' timestamp")
    
    return errors


def _merge_to_sqlite(symbol: str, scrape_data: dict):
    """Merge scraped financial data into SQLite (red zone tables)."""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        name = scrape_data.get("nume", symbol)
        upsert_company(conn, symbol, name)
        log.debug(f"[scrape] {symbol} — company ensured")

        quarterly = scrape_data.get("quarterly", [])
        if quarterly:
            entries = []
            for q in quarterly:
                items = q.get("items", {})
                entries.append({
                    "date": q.get("date", ""),
                    "revenue": items.get("Total Revenue"),
                    "net_income": items.get("Net Income"),
                    "source": q.get("_note", scrape_data.get("source", "scraping_webhook")),
                })
            upsert_quarterly(conn, symbol, entries)
            log.info(f"[scrape] {symbol} — {len(entries)} quarterly entries upserted")

        annual = scrape_data.get("annual", [])
        if annual:
            entries = []
            for a in annual:
                items = a.get("items", {})
                entries.append({
                    "date": a.get("date", ""),
                    "revenue": items.get("Total Revenue"),
                    "net_income": items.get("Net Income"),
                    "source": a.get("_note", scrape_data.get("source", "scraping_webhook")),
                })
            upsert_annual(conn, symbol, entries)
            log.info(f"[scrape] {symbol} — {len(entries)} annual entries upserted")

        metrics = scrape_data.get("metrics", {})
        if metrics:
            # Filter out non-scalar values (e.g. eps as dict from agent)
            clean_metrics = {
                k: v for k, v in metrics.items()
                if isinstance(v, (int, float, type(None)))
            }
            if clean_metrics:
                upsert_metrics(conn, symbol, clean_metrics)
                log.info(f"[scrape] {symbol} — metrics upserted: {list(clean_metrics.keys())}")
            skipped = [k for k in metrics if k not in clean_metrics]
            if skipped:
                log.warning(f"[scrape] {symbol} — skipped non-scalar metrics: {skipped}")

        conn.commit()
        log.info(f"[scrape] {symbol} — committed, calculating metrics...")

        # Calculate metrics from available data
        from metrics_calculator import calc_metrics
        calc_metrics(conn, symbol)
        log.info(f"[scrape] {symbol} — metrics calculated")
    except Exception as e:
        conn.rollback()
        log.error(f"[scrape] {symbol} — SQLite merge FAILED: {e}")
        raise
    finally:
        conn.close()


def _update_pending_status(symbol: str, status: str):
    if not os.path.exists(PENDING_SCRAPES_FILE):
        return
    with open(PENDING_SCRAPES_FILE, "r", encoding="utf-8") as f:
        pending = json.load(f)
    for task in pending.get("tasks", []):
        if task.get("symbol") == symbol:
            task["status"] = status
            log.debug(f"[scrape] {symbol} — pending status → {status}")
    with open(PENDING_SCRAPES_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def _remove_pending_task(symbol: str):
    if not os.path.exists(PENDING_SCRAPES_FILE):
        return
    with open(PENDING_SCRAPES_FILE, "r", encoding="utf-8") as f:
        pending = json.load(f)
    pending["tasks"] = [t for t in pending.get("tasks", []) if t.get("symbol") != symbol]
    log.info(f"[scrape] {symbol} — removed from pending queue")
    with open(PENDING_SCRAPES_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global streamer
    from db import init_db
    init_db() # Migrate schema if needed
    from shared.tradeville_streamer import TradevilleStreamer
    streamer = TradevilleStreamer()
    streamer.start()
    
    server = HTTPServer((SERVER_HOST, SERVER_PORT), DashboardHandler)
    log.info(f"BVB Dashboard API on http://{SERVER_HOST}:{SERVER_PORT}")
    log.info(f"Logging to {LOG_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()
    finally:
        if streamer:
            streamer.stop()

if __name__ == "__main__":
    main()
