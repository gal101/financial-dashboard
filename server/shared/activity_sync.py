import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "server"))

from db import get_db

def sync_activities(client):
    """Sync account transactions from Tradeville and populate SQLite user_transactions table."""
    # 1. Determine start_date
    conn = get_db()
    start_date_str = "1jan19"
    try:
        row = conn.execute("SELECT MAX(date) FROM user_transactions").fetchone()
        if row and row[0]:
            dt = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
            # Go back 1 day to handle same-day timing variations safely
            start_date = dt.date() - timedelta(days=1)
            start_date_str = client.format_date(start_date)
    except Exception as e:
        print(f"[sync] Error determining last sync date: {e}")
    finally:
        conn.close()
        
    print(f"[sync] Fetching activities from Tradeville since {start_date_str}...")
    
    # 2. Query Tradeville via server proxy
    res = client.send_request({
        "cmd": "Activity",
        "prm": {
            "symbol": None,
            "dstart": start_date_str,
            "dend": None
        }
    })
    
    if "data" not in res or res.get("is_offline"):
        print("[sync] Local Tradeville Proxy is down or WebSocket offline. Sync skipped.")
        return
        
    data = res["data"]
    dates = data.get("Date", [])
    op_types = data.get("OpType", [])
    symbols = data.get("Symbol", [])
    quantities = data.get("Quantity", [])
    prices = data.get("Price", [])
    commissions = data.get("Comission", []) # Tradeville schema Comission
    amounts = data.get("Ammount", [])      # Tradeville schema Ammount
    
    inserted = 0
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for i in range(len(dates)):
            date_val = dates[i]
            op_type = op_types[i]
            symbol = symbols[i] if i < len(symbols) else None
            qty = quantities[i] if i < len(quantities) else None
            price = prices[i] if i < len(prices) else None
            comm = commissions[i] if i < len(commissions) else None
            amt = amounts[i] if i < len(amounts) else None
            
            # Check if transaction already exists to avoid duplicates
            dup = conn.execute(
                "SELECT 1 FROM user_transactions WHERE date = ? AND op_type = ? AND symbol = ? AND amount = ?",
                (date_val, op_type, symbol, amt)
            ).fetchone()
            
            if not dup:
                conn.execute(
                    "INSERT INTO user_transactions (date, op_type, symbol, quantity, price, commission, amount) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (date_val, op_type, symbol, qty, price, comm, amt)
                )
                inserted += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[sync] Error writing user transactions: {e}")
    finally:
        conn.close()
        
    print(f"[sync] Synced {inserted} new transactions successfully.")

if __name__ == "__main__":
    from shared.tradeville_client import TradevilleClient
    with TradevilleClient() as client:
        sync_activities(client)
