import sys
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "back-end"))

from shared.tradeville_client import TradevilleClient

with TradevilleClient() as client:
    res = client.send_request({
        "cmd": "Portfolio",
        "prm": {"data": None}
    })
    if "data" in res:
        data = res["data"]
        for i in range(len(data['Symbol'])):
            print(data['Symbol'][i], data['PType'][i])
