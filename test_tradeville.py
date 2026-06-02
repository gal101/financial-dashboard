import sys
import os
from datetime import datetime, timedelta

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.join(script_dir, "server")
sys.path.insert(0, server_dir)

from shared.tradeville_client import TradevilleClient

def main():
    print("Testing TradevilleClient integration...")
    with TradevilleClient() as client:
        print("\n1. Fetching current details for TLV:")
        tlv_price = client.get_symbol_price("TLV")
        print(tlv_price)
        
        print("\n2. Fetching historical prices for BRD (last 3 days):")
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=5) # 5 days to ensure at least 3 business days
        brd_history = client.get_daily_values("BRD", start_date, end_date)
        print(f"Total price rows fetched: {len(brd_history)}")
        for row in brd_history[-3:]:
            print(row)
            
        print("\n3. Fetching historical prices for TLV (last 3 days):")
        tlv_history = client.get_daily_values("TLV", start_date, end_date)
        print(f"Total price rows fetched for TLV: {len(tlv_history)}")
        for row in tlv_history[-3:]:
            print(row)

if __name__ == "__main__":
    main()
