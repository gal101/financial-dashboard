import os
import queue
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import pytz
import dotenv
import websocket

log = logging.getLogger("bvb-server")

class TradevilleStreamer(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        
        # Load env
        dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
        
        self.out_queue = queue.Queue()
        self.pending_requests = {}
        self.push_queue = queue.Queue()
        self.price_cache = {}
        self.last_volz = {}
        self.active_tickers = set()
        self.authenticated = False
        
        self.worker_pool = ThreadPoolExecutor(max_workers=4)
        self.ws = None
        
    def run(self):
        # Start helper threads
        threading.Thread(target=self._transmitter_loop, daemon=True).start()
        threading.Thread(target=self._daily_reset_loop, daemon=True).start()
        threading.Thread(target=self._push_worker_loop, daemon=True).start()
        
        # Connection loop
        user = os.getenv("TRADEVILLE_USER")
        password = os.getenv("TRADEVILLE_PASSWORD")
        demo_str = os.getenv("TRADEVILLE_DEMO", "true").lower()
        demo = demo_str == "true"
        
        if not user or not password:
            log.error("[tradeville] Missing credentials in .env file.")
            return
            
        backoff = 1.0
        while self.running:
            try:
                log.info("[tradeville] Connecting to wss://api.tradeville.ro:443...")
                self.ws = websocket.create_connection("wss://api.tradeville.ro:443", subprotocols=["apitv"])
                backoff = 1.0 # Reset backoff
                
                # Start receiver loop in its own thread to handle authentication response
                receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
                receiver_thread.start()
                
                # Perform login
                login_payload = {
                    "cmd": "login",
                    "prm": {
                        "coduser": user,
                        "parola": password,
                        "demo": demo
                    }
                }
                event = threading.Event()
                self.pending_requests[("login", None)] = {"event": event, "response": None}
                self.out_queue.put(login_payload)
                
                if not event.wait(timeout=10):
                    raise TimeoutError("Login timeout")
                
                response = self.pending_requests.pop(("login", None), {}).get("response")
                if not response or response.get("OK") != 1:
                    raise ValueError(f"Login failed: {response}")
                self.authenticated = True
                log.info("[tradeville] Authenticated successfully.")
                
                # Resubscribe to active tickers if any
                self._resubscribe()
                
                # Wait for receiver loop to finish (e.g. on disconnect)
                receiver_thread.join()
            except ValueError as e:
                log.error(f"[tradeville] WebSocket login failed (auth/access issue): {e}")
                time.sleep(300.0) # Sleep 5 minutes to avoid rate limit spamming
            except Exception as e:
                log.error(f"[tradeville] WebSocket connection error: {e}")
                time.sleep(backoff)
                backoff = min(60.0, backoff * 2.0)
                
    def _transmitter_loop(self):
        last_sent_time = 0
        while self.running:
            try:
                payload = self.out_queue.get(timeout=1)
            except queue.Empty:
                continue
                
            cmd = payload.get("cmd")
            # If we are subscribing, keep track of symbols
            if cmd == "subscribe":
                syms = payload.get("sym")
                if syms:
                    for s in syms.split(","):
                        s = s.strip()
                        if s:
                            self.active_tickers.add(s)
                            
            # Calculate cooldown (strict 0.6s to respect rate limits)
            now = time.time()
            elapsed = now - last_sent_time
            sleep_time = max(0.0, 0.6 - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
                
            try:
                if self.ws and self.ws.connected:
                    self.ws.send(json.dumps(payload))
                    last_sent_time = time.time()
                    log.info(f"[tradeville] Sent command: {cmd}")
                else:
                    # Put it back in queue and sleep
                    self.out_queue.put(payload)
                    time.sleep(0.5)
            except Exception as e:
                log.error(f"[tradeville] Error sending command: {e}")
                self.out_queue.put(payload)
                self.force_reconnect()
                time.sleep(1.0)
                
    def _receiver_loop(self):
        while self.running:
            try:
                msg = self.ws.recv()
                log.info(f"[tradeville] Received raw message: {msg}")
                if not msg:
                    log.info("[tradeville] WebSocket closed by server.")
                    break
                    
                response = json.loads(msg)
                
                if response.get("updtype") == "CA":
                    self.push_queue.put(response)
                    continue
                    
                cmd = response.get("cmd")
                if not cmd:
                    continue
                    
                # Match request
                symbol = None
                data = response.get("data")
                if isinstance(data, dict):
                    symbols = data.get("Symbol")
                    if symbols and len(symbols) > 0:
                        symbol = symbols[0]
                elif "sym" in response:
                    symbol = response.get("sym")
                    
                key = (cmd, symbol)
                target_key = None
                if key in self.pending_requests:
                    target_key = key
                elif (cmd, None) in self.pending_requests:
                    target_key = (cmd, None)
                else:
                    for k in list(self.pending_requests.keys()):
                        if k[0] == cmd:
                            target_key = k
                            break
                            
                if target_key:
                    req = self.pending_requests[target_key]
                    req["response"] = response
                    req["event"].set()
                    
            except Exception as e:
                log.error(f"[tradeville] Receiver loop error: {e}")
                break
                
    def _daily_reset_loop(self):
        while self.running:
            tz = pytz.timezone("Europe/Bucharest")
            now = datetime.now(tz)
            target = now.replace(hour=9, minute=40, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)
            sleep_secs = (target - now).total_seconds()
            log.info(f"[tradeville] Daily reset scheduled in {sleep_secs} seconds (at {target})")
            
            while sleep_secs > 0 and self.running:
                sleep_time = min(10, sleep_secs)
                time.sleep(sleep_time)
                sleep_secs -= sleep_time
                
            if self.running:
                log.info("[tradeville] Performing scheduled daily reset at 09:40 EEST...")
                self.force_reconnect()
                
    def _push_worker_loop(self):
        while self.running:
            try:
                tick = self.push_queue.get(timeout=1)
            except queue.Empty:
                continue
            self.worker_pool.submit(self._process_push_tick, tick)
            
    def _process_push_tick(self, tick):
        symbol = tick.get("sim")
        if not symbol:
            return
        price = tick.get("pret")
        volz = tick.get("volz") or 0
        
        # Update memory cache
        self.price_cache[symbol] = tick
        
        # Calculate volz_diff
        old_volz = self.last_volz.get(symbol)
        if old_volz is None:
            # Try SQLite
            from db import get_db
            conn = get_db()
            try:
                tz = pytz.timezone("Europe/Bucharest")
                today = datetime.now(tz).strftime("%Y-%m-%d")
                row = conn.execute(
                    "SELECT volume FROM price_history WHERE symbol = ? AND date = ?",
                    (symbol, today)
                ).fetchone()
                if row:
                    old_volz = row["volume"] or 0
                else:
                    old_volz = volz
            except Exception as e:
                log.error(f"[tradeville] Error reading volume: {e}")
                old_volz = volz
            finally:
                conn.close()
            self.last_volz[symbol] = old_volz
            
        volz_diff = volz - old_volz
        self.last_volz[symbol] = volz
        
        # Update SQLite price history
        from db import get_db
        conn = get_db()
        try:
            tz = pytz.timezone("Europe/Bucharest")
            today = datetime.now(tz).strftime("%Y-%m-%d")
            
            row = conn.execute(
                "SELECT open, high, low, close, volume FROM price_history WHERE symbol = ? AND date = ?",
                (symbol, today)
            ).fetchone()
            
            if row:
                new_high = max(row["high"] or price, price)
                new_low = min(row["low"] or price, price)
                conn.execute(
                    "UPDATE price_history SET close = ?, high = ?, low = ?, volume = ? WHERE symbol = ? AND date = ?",
                    (price, new_high, new_low, volz, symbol, today)
                )
            else:
                conn.execute(
                    "INSERT INTO price_history (symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (symbol, today, price, price, price, price, volz)
                )
            conn.commit()
        except Exception as e:
            log.error(f"[tradeville] Error updating price history: {e}")
        finally:
            conn.close()
            
    def _resubscribe(self):
        if self.active_tickers:
            syms_str = ",".join(self.active_tickers)
            log.info(f"[tradeville] Resubscribing to active tickers: {syms_str}")
            subscribe_payload = {
                "cmd": "subscribe",
                "sym": syms_str,
                "prm": {}
            }
            self.out_queue.put(subscribe_payload)
            
    def force_reconnect(self):
        log.info("[tradeville] Forcing reconnect...")
        self.authenticated = False
        try:
            if self.ws:
                self.ws.close()
        except Exception as e:
            log.debug(f"[tradeville] Error closing socket: {e}")
    def stop(self):
        self.running = False
        self.authenticated = False
        self.force_reconnect()
        self.worker_pool.shutdown(wait=False)