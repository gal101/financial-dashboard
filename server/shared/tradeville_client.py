import requests
import logging
from datetime import date

log = logging.getLogger("bvb-server")

class ProxyDownException(Exception):
    pass

class TradevilleClient:
    def __init__(self):
        self.session = None

    def __enter__(self):
        self.session = requests.Session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
            self.session = None

    def send_request(self, payload: dict) -> dict:
        url = "http://127.0.0.1:8089/api/tradeville/request"
        session = self.session if self.session else requests
        try:
            response = session.post(url, json=payload, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            log.warning(f"[offline] Local Tradeville Proxy is down: {e}")
            return {"error": "offline", "is_offline": True}

    def format_date(self, d) -> str:
        month_map = {
            1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "may", 6: "jun",
            7: "jul", 8: "aug", 9: "sep", 10: "oct", 11: "nov", 12: "dec"
        }
        day = d.day
        month = month_map[d.month]
        year = str(d.year)[2:]
        return f"{day}{month}{year}"

    def get_symbol_price(self, symbol: str) -> dict:
        return self.send_request({
            "cmd": "Symbol",
            "prm": {
                "symbol": symbol
            }
        })

    def get_daily_values(self, symbol: str, start_date, end_date = None) -> list:
        res = self.send_request({
            "cmd": "DailyValues",
            "prm": {
                "symbol": symbol,
                "dstart": self.format_date(start_date),
                "dend": self.format_date(end_date) if end_date else None,
                "adj": 1
            }
        })
        data = res.get("data")
        if not data or not isinstance(data, dict) or "Date" not in data:
            return []
        
        dates = data.get("Date") or []
        opens = data.get("Open") or []
        highs = data.get("High") or []
        lows = data.get("Low") or []
        closes = data.get("Close") or []
        volumes = data.get("Volume") or []
        values = data.get("Value") or []
        
        out = []
        for i in range(len(dates)):
            out.append({
                "date": dates[i],
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": closes[i] if i < len(closes) else None,
                "volume": volumes[i] if i < len(volumes) else None,
                "value": values[i] if i < len(values) else None
            })
        return out
