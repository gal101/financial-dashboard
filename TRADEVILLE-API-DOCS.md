# Tradeville API Documentation for BVB Financial Dashboard

This document details the Tradeville WebSocket API commands, their use cases for the dashboard, and the JSON payload formats for both requests and responses.

All communications happen over a WebSocket connection to:
`wss://api.tradeville.ro:443` using the subprotocol `apitv`.

---

## 1. Commands Overview & Use Cases

| Command | Request Type | Use Case in Dashboard |
| :--- | :--- | :--- |
| **`login`** | Authentication | Required once per connection before sending any other commands. Supports both demo and real accounts. |
| **`Portfolio`** | Request-Response | Automated synchronisation of user holdings (symbols, quantities, buy prices) directly from their Tradeville account. |
| **`Activity`** | Request-Response | Automatic realized profit/loss calculations and automatic logging of received dividend payments. |
| **`Orders`** | Request-Response | Displays a list of active/pending broker orders in a dashboard widget. |
| **`Symbol`** | Request-Response | Fetches real-time price, bid/ask spread, volume, total outstanding shares, and earnings for a ticker. |
| **`subscribe`** | Stream Subscription | Registers the client to receive automatic real-time push price updates for specified tickers. |
| **`Level2`** | Request-Response | Fetches the full market depth (order book) showing top 10 bids/asks for the company profile page. |
| **`DailyValues`** | Request-Response | Downloads daily historical stock prices (OHLCV) to populate charts and tables on the company profile. |
| **`Trades`** | Request-Response | Retrieves the tick-by-tick time & sales transactions of the current session to render trade history lists or volume profiles. |
| **`SearchSymbol`** | Request-Response | Search BVB symbols by company name to autocomplete queries when adding tickers to a watchlist. |

---

## 2. JSON Payloads & Schema Reference

### 1. `login`
Used to authenticate the WebSocket session. Must be called immediately after connection establishment.

* **Request Payload:**
  ```json
  {
    "cmd": "login",
    "prm": {
      "coduser": "!DemoAPITDV",
      "parola": "DemoAPITDV",
      "demo": true
    }
  }
  ```
* **Response Payload (Success):**
  ```json
  {
    "cmd": "login",
    "OK": 1
  }
  ```

---

### 2. `Portfolio`
Retrieves all active assets in the authenticated broker account.

* **Request Payload:**
  ```json
  {
    "cmd": "Portfolio",
    "prm": {
      "data": null
    }
  }
  ```
  *(Note: A string date can be passed to `data` to query history, or `null` for the current portfolio state.)*
* **Response Payload:**
  ```json
  {
    "cmd": "Portfolio",
    "data": {
      "Account": ["!DEMOAPITDV", "!DEMOAPITDV", "!DemoAPITDV"],
      "Symbol": ["AAG", "BRD", "RON"],
      "Quantity": [5003, 100, 16622.1851],
      "AvgPrice": [2.996687889, 14.35996818, 0],
      "MarketPrice": [3.16, 14.02, 1],
      "PType": ["A", "A", "B"],
      "Ccy": ["RON", "RON", "RON"]
    }
  }
  ```

---

### 3. `Activity`
Retrieves past transactions and events associated with the account.

* **Request Payload:**
  ```json
  {
    "cmd": "Activity",
    "prm": {
      "symbol": null,
      "dstart": "1oct19",
      "dend": "10oct19"
    }
  }
  ```
* **Response Payload:**
  ```json
  {
    "cmd": "Activity",
    "data": {
      "Date": ["2019-10-07T17:25:27.980Z", "2019-10-07T17:20:40.560Z"],
      "OpType": ["Buy", "In"],
      "Symbol": ["CEON", "RON"],
      "Quantity": [10000, 50000],
      "Price": [0.355, null],
      "Comission": [17.75, null],
      "Ammount": [-3569.88, 50000],
      "CashPos": [16622.1851, 66622.1851]
    }
  }
  ```
  *(Note: `Ammount` is negative for Buy orders and positive for Sell orders / Cash Deposits (`In`).)*

---

### 4. `Orders`
Retrieves the active pending orders placed on BVB.

* **Request Payload:**
  ```json
  {
    "cmd": "Orders",
    "prm": {
      "symbol": "AAG",
      "dstart": null
    }
  }
  ```
* **Response Payload:**
  ```json
  {
    "cmd": "Orders",
    "data": {
      "OrderId": ["A312673"],
      "Symbol": ["AAG"],
      "Status": ["S"],
      "TrdStatus": ["suspendat"],
      "Date": ["2019-10-07T18:17:00.493Z"],
      "OpType": ["Buy"],
      "ActiveQty": [1],
      "Quantity": [1],
      "Price": [1.5],
      "NetPrice": [null],
      "NewPrice": [null]
    }
  }
  ```

---

### 5. `Symbol`
Gets current pricing information, BVB limit thresholds, and registrar financials for a specific ticker.

* **Request Payload:**
  ```json
  {
    "cmd": "Symbol",
    "prm": {
      "symbol": "BRD"
    }
  }
  ```
* **Response Payload:**
  ```json
  {
    "cmd": "Symbol",
    "data": {
      "Symbol": ["BRD"],
      "Price": [14.46],
      "RefPrice": [14.8],
      "BidQ": [3264],
      "Bid": [14.44],
      "Ask": [14.46],
      "AskQ": [155],
      "DayVolume": ["336937"],
      "DayValue": [4849228.5],
      "DayMin": [14.0],
      "DayMax": [14.68],
      "LimitDown": [11.1001],
      "LimitUp": [18.5],
      "Status": ["Opened"],
      "Market": ["(BVB) REGS"],
      "Ccy": ["RON"],
      "ISIN": ["ROBRDBACNOR2"],
      "Name": ["BRD - Groupe Societe Generale"],
      "SharesNr": [696901518],
      "Earnings": [962857000.0],
      "EarnDate": ["2020-12-31"],
      "StatusM": ["Ready"]
    }
  }
  ```

---

### 6. `subscribe`
Abonarea la fluxul live de cotații pentru unul sau mai multe simboluri.

* **Subscription Request Payload:**
  ```json
  {
    "cmd": "subscribe",
    "sym": "BRD,TLV,SNP",
    "prm": {},
    "OK": 1
  }
  ```
* **Subscription Response Confirmation:**
  ```json
  {
    "cmd": "subscribe",
    "sym": "BRD,TLV,SNP",
    "OK": 1
  }
  ```
* **Real-time Push Message Payload:**
  Sent by the server automatically when a trade or spread update occurs for subscribed symbols.
  ```json
  {
    "updtype": "CA",
    "sim": "TLV",
    "pret": 2.205,
    "bid": 2.2,
    "ask": 2.205,
    "cbid": 1552,
    "cask": 75057,
    "volz": 1175332,
    "valz": 2592291,
    "ref": 2.22
  }
  ```

---

### 7. `Level2` (Market Depth / Order Book)
Gets current market depth showing active buyer and seller interest at the top 10 pricing levels.

* **Request Payload:**
  ```json
  {
    "cmd": "Level2",
    "prm": {
      "symbol": "BRD"
    }
  }
  ```
* **Response Payload:**
  ```json
  {
    "cmd": "Level2",
    "data": {
      "BidNo": [2, 2, 1, 3],
      "BidQ": [3264, 1242, 29, 5337],
      "Bid": [14.44, 14.42, 14.40, 14.36],
      "Ask": [14.48, 14.50, 14.52, 14.54],
      "AskQ": [4519, 12440, 1166, 825],
      "AskNo": [9, 6, 2, 1],
      "BidH": ["", "", "", ""],
      "AskH": ["", "", "", ""]
    }
  }
  ```

---

### 8. `DailyValues` (Historical Prices)
Retrieves daily stock price records. Essential for rendering charts.

* **Request Payload:**
  ```json
  {
    "cmd": "DailyValues",
    "prm": {
      "symbol": "BRD",
      "dstart": "1jan19",
      "dend": null,
      "adj": 1
    }
  }
  ```
  *(Note: Set `adj` to `1` to receive split-adjusted history.)*
* **Response Payload:**
  ```json
  {
    "cmd": "DailyValues",
    "data": {
      "Symbol": ["BRD", "BRD", "BRD"],
      "Date": ["2020-11-02", "2020-11-03", "2020-11-04"],
      "Open": [11.42, 11.76, 12.06],
      "Low": [11.42, 11.76, 11.88],
      "High": [12.00, 12.04, 12.24],
      "Close": [11.72, 12.04, 12.24],
      "Volume": [116600, 71969, 57774]
    }
  }
  ```

---

### 9. `Trades`
Retrieves tick-by-tick public transaction logs from the current session.

* **Request Payload:**
  ```json
  {
    "cmd": "Trades",
    "prm": {
      "symbol": "BRD",
      "dstart": "16oct19",
      "dend": "20oct19"
    }
  }
  ```
* **Response Payload:**
  ```json
  {
    "cmd": "Trades",
    "data": {
      "Symbol": ["BRD", "BRD"],
      "Date": ["2019-10-16T10:00:00.513Z", "2019-10-16T10:06:46.297Z"],
      "Price": [14.30, 14.32],
      "Volume": [200, 1500],
      "Trades": [1, 2],
      "Agres": ["B", "S"],
      "BidQ": [150, 400],
      "Bid": [14.28, 14.30],
      "Ask": [14.30, 14.32],
      "AskQ": [200, 1200]
    }
  }
  ```
  *(Note: `Agres` indicates who initiated the execution - "B" for Buyer aggressive, "S" for Seller aggressive.)*

---

### 10. `SearchSymbol`
Provides search autocomplete suggestions for BVB listings.

* **Request Payload:**
  ```json
  {
    "cmd": "SearchSymbol",
    "prm": {
      "search": "electric"
    }
  }
  ```
* **Response Payload:**
  ```json
  {
    "cmd": "SearchSymbol",
    "data": {
      "Symbol": ["SNN", "EL", "TEL"],
      "Name": [
        "S.N. NUCLEARELECTRICA S.A.",
        "SOCIETATEA ENERGETICA ELECTRICA S.A.",
        "C.N.T.E.E. TRANSELECTRICA"
      ]
    }
  }
  ```
