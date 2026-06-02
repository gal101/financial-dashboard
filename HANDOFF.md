# Tradeville API Migration — Step-by-Step Handoff Document

This document outlines the step-by-step migration process from Yahoo Finance (`yfinance`) to the Tradeville API. This is prepared for the next agent/developer to execute.

---

## 1. Prerequisites & Dependencies

Add the following packages to `financial-dashboard/server/requirements.txt`:
- `websocket-client>=1.3.0` (required for WebSocket communication with Tradeville)
- `python-dotenv>=1.0.0` (required to load credentials from `.env`)

---

## 2. Step-by-Step Migration Plan

### Step 1: Implement Credentials Setup Scripts
Create two interactive CLI setup files in the repository root to prompt the user for credentials and write them to a `.env` file:

1. **`setup_credentials.py` (Python):**
   - Import `os`.
   - Interactively prompt the user using `input()` for:
     - `TRADEVILLE_USER` (Default: `!DemoAPITDV`)
     - `TRADEVILLE_PASSWORD` (Default: `DemoAPITDV`)
     - `TRADEVILLE_DEMO` (Default: `true` if empty, parsed as lowercase string `"true"` or `"false"`)
   - Write these key-value pairs into a `.env` file in the repository root.
2. **`setup_credentials.sh` (Bash):**
   - Implement the same interactive prompt in Bash using `read -p`.
   - Write/overwrite the `.env` file.
   - Run `chmod +x setup_credentials.sh` so it is executable.

### Step 2: Implement the Shared `TradevilleClient`
Create `financial-dashboard/server/shared/tradeville_client.py`. This is a lightweight helper used by CLI scripts (`company_fetcher.py`, `portfolio_updater.py`) to query Tradeville via the local server proxy, avoiding direct WebSocket handshakes.

* **Class Design:** `class TradevilleClient:`
* **Context Manager Support:** Implement `__enter__(self)` and `__exit__(self, exc_type, exc_val, exc_tb)`.
  - It does NOT connect to Tradeville. It simply initializes a connection session to the local HTTP server.
* **Helper Functions:**
  - `send_request(self, payload: dict) -> dict`: Sends a POST request to `http://localhost:8089/api/tradeville/request` with the payload as JSON, and returns the parsed JSON response.
    * **Offline Safety:** Wrap the POST call in a `try...except requests.exceptions.RequestException` block. If the local proxy server is stopped (e.g. `ConnectionRefusedError` or timeout), log `[offline] Local Tradeville Proxy is down` and return `{"error": "offline"}` or raise a custom `ProxyDownException`.
  - `format_date(self, d: date) -> str`: Converts a Python `date`/`datetime` object into `<day><month_3_letters_english_lowercase><year_2_digits>` (e.g. `2jun21`).
  - `get_symbol_price(self, symbol: str) -> dict`: Calls `self.send_request({ "cmd": "Symbol", "prm": { "symbol": symbol } })`.
  - `get_daily_values(self, symbol: str, start_date: date, end_date: date = None) -> list`: Calls `self.send_request({ "cmd": "DailyValues", "prm": { "symbol": symbol, "dstart": self.format_date(start_date), "dend": self.format_date(end_date) if end_date else None } })`.

### Step 3: Implement Verification Script `test_tradeville.py`
Create a test script `test_tradeville.py` in the root directory:
- It should load the `.env` credentials.
- Use the `TradevilleClient` context manager.
- Fetch current details for `TLV` using `get_symbol_price`.
- Fetch 3 days of historical prices for `BRD` using `get_daily_values`.
- Print outputs to console to verify login, connection, and parser logic work correctly.

### Step 4: Update `portfolio_updater.py`
Refactor `portfolio_updater.py` to use `TradevilleClient`:
1. Support targeted updates: Check for specific tickers passed as CLI arguments (e.g. `sys.argv[1:]`). If present, only update those tickers; otherwise, update all tickers loaded from `bvb_portfolio.json` and `watchlist.json`.
2. Remove `import yfinance as yf`.
3. Remove `yahoo_symbol` mapping and `.RO` suffix additions. Run queries directly with clean tickers (e.g., `TLV`, `EBTLVTL19`).
4. Inside the `main()` loop, wrap the symbol updates inside a `with TradevilleClient() as client:` context to reuse the connection.
5. Replace `fetch_price(sim)`. In the refactored version:
   - Call `client.get_symbol_price(sim)`.
   - Parse Tradeville's response (see response structure cheat sheet below).
   - If the response is valid, calculate the percentage change:
     $$\text{change\_pct} = \frac{\text{price} - \text{ref\_price}}{\text{ref\_price}} \times 100$$
   - Map this to the portfolio JSON holdings fields: `pret_actual_RON`, `variatie_pret_pct`, `valoare_evaluata_RON`, and `profit_pierdere_RON`.

### Step 5: Update `company_fetcher.py`
Refactor `company_fetcher.py` to fetch historical price history and metadata from Tradeville:
1. Support targeted updates: Check for specific tickers passed as CLI arguments. If present, only process those tickers; otherwise, process all tickers loaded from `bvb_portfolio.json` and `watchlist.json`.
2. Replace `yf.Ticker(ysym).history(period="5y")` with `client.get_daily_values(sym, start_date=five_years_ago)`.
3. Update `db.py` Schema & Queries: Add `open`, `high`, `low`, and `volume` columns to `price_history` schema. Update `upsert_prices`, `get_company` queries, and `export_to_json` in `db.py` to handle these new fields.
4. Fetch structural metadata: For each target symbol, call `client.get_symbol_price(sym)` to retrieve `SharesNr`, `Earnings`, `EarnDate`, `Name`, and `ISIN`. Upsert these values into the SQLite `companies` and `calculated_metrics` tables.
5. Map the Tradeville response list to the SQLite table `price_history` structure. Tradeville dates are standard ISO strings `"YYYY-MM-DD"`.
6. Extract and save raw `open`, `high`, `low`, `volume`, and `close` values directly to the SQLite `price_history` table.

### Step 6: Implement the Centralized Gateway (`TradevilleStreamer`)
Create `financial-dashboard/server/shared/tradeville_streamer.py`. This runs a persistent WebSocket daemon in the background of `server.py`:
* **Class Design:** `class TradevilleStreamer(threading.Thread):`
* **Shared Resources:**
  - `self.out_queue = queue.Queue()`: For outgoing requests.
  - `self.pending_requests = {}`: A dict mapping `(cmd, correlation_id)` (e.g. `('Symbol', 'BRD')`) to a dict `{"event": threading.Event(), "response": None}`.
  - `self.push_queue = queue.Queue()`: For processing push notifications in parallel.
  - `self.worker_pool = ThreadPoolExecutor(max_workers=4)`: To process push data in parallel worker threads.
* **Operation Threads:**
  1. **Connection & Login:** Connects to `wss://api.tradeville.ro:443` (protocol `apitv`) using credentials loaded from `.env` (or demo credentials fallback). Authenticates with the `login` command.
  2. **Transmitter Loop (Thread):** Pulls commands from `self.out_queue`. Enforces a strict `0.5s` delay between consecutive WebSocket sends to guarantee we never exceed the 20 requests per 10 seconds limit.
  3. **Receiver Loop (Thread):** Reads from `self.ws.recv()`.
     - **If command response:** Matches the incoming command (e.g., `cmd: "DailyValues"`) and symbol to a pending request in `self.pending_requests`. Populates the response object and triggers `.set()` on the corresponding `Event` to wake up the waiting HTTP thread.
     - **If push message (`updtype: "CA"`):** Drops the message immediately into `self.push_queue` for worker threads to process in parallel, ensuring the socket receive buffer never blocks.
  4. **Push Processing Workers:** Thread pool workers pull from `self.push_queue`, parse the tick (`pret`, `volz`, `ref`), compute changes ($\text{volz\_diff} = \text{volz} - \text{old\_volz}$), and update the memory cache and SQLite price history.
  5. **Auto-Reconnect:** Implements infinite reconnect loop with exponential backoff. On reconnect, it auto-logs in and sends a `subscribe` command for all active symbols.
  6. **Daily Reset:** Triggers a clean reconnect/resubscribe once a day before market open (09:40 EEST).
### Step 7: Update `server.py` & Handlers
1. **`server.py` HTTP Proxy Endpoint:**
   - Add a `POST /api/tradeville/request` handler:
     1. Receives the JSON payload.
     2. Registers a `threading.Event()` in `streamer.pending_requests` for this request key.
     3. Appends the request to `streamer.out_queue`.
     4. Blocks on `Event.wait(timeout=10)`.
     5. Returns the populated response JSON (or timeout error).
2. **`server.py` Streamer Boot:**
2. **Watchlist & Portfolio Refreshes:**
   - Modify `_fetch_watchlist_prices` in `refresh.py` to immediately read values from the `TradevilleStreamer` cache instead of querying BVB. This makes the dashboard page loading and refresh requests instant.
   - Modify `portfolio_updater.py` or its triggers to pull from the cached streaming values as the primary source of truth, avoiding outbound network calls during user interaction.
3. **Watchlist Addition Optimization:**
   - In `server/handlers/watchlist.py`, update `_fetch_price_for(symbol)` to run `portfolio_updater.py <symbol>` and `company_fetcher.py <symbol>` as subprocesses targeting *only* that symbol. This fetches the pricing, history, and structural metadata for the new watchlist company immediately, without wasting requests on existing symbols.

### Step 8: Implement Frontend Dual-Chart View (Line ↔ Min-Max Range)
1. **UI Layout Updates (`company.html`):**
   - In `company.html`, add a toggle button group `#ch-type-btns` next to the `#ch-period-btns` group:
     ```html
     <div class="ch-btn-group" id="ch-type-btns">
       <button class="on" data-type="line">Linie</button>
       <button data-type="range">Min-Max</button>
     </div>
     ```
2. **Toggle Javascript Logic (`company_profile.js`):**
   - Define a global state variable `var chartType = 'line';`.
   - Add click event listener to `#ch-type-btns button`:
     - Toggle class `on` between buttons.
     - Update `chartType` to matching dataset type (`line` or `range`).
     - Call `renderPriceChart()` to redraw the chart.
3. **Chart Rendering Updates (`renderPriceChart`):**
   - In `renderPriceChart()`, compile a **Volume dataset** to serve as a discrete background overlay, and then conditionalise the pricing datasets compilation based on `chartType`:
     * **Volume Dataset (Always present):**
       ```javascript
       {
         type: 'bar',
         label: 'Volum',
         data: prices.map(function(p) { return p.volume || 0; }),
         backgroundColor: 'rgba(59, 130, 246, 0.15)', // light blue overlay
         borderColor: 'transparent',
         yAxisID: 'yVolume',
         order: 3
       }
       ```
     * **If `chartType === 'line'`:** Use a single line dataset with `data: prices.map(p => p.close)` (mapped to primary Y-axis `y`, `order: 1`).
     * **If `chartType === 'range'`:** Compile two datasets:
       - **Dataset 1 (floating bar representing High-Low):**
         ```javascript
         {
           type: 'bar',
           label: 'Interval Min-Max',
           data: prices.map(function(p) {
             var low = (p.low !== undefined && p.low !== null) ? p.low : p.close;
             var high = (p.high !== undefined && p.high !== null) ? p.high : p.close;
             return [low, high];
           }),
           backgroundColor: 'rgba(139, 143, 163, 0.3)',
           borderColor: 'rgba(139, 143, 163, 0.7)',
           borderWidth: 1,
           barThickness: 2, // makes the bar thin like a wick
           order: 2
         }
         ```
       - **Dataset 2 (scatter dots representing Close):**
         ```javascript
         {
           type: 'line',
           label: 'Preț Închidere',
           data: prices.map(function(p) { return p.close; }),
           borderColor: color,
           borderWidth: 0,
           pointRadius: 2,
           showLine: false, // only show points, do not draw connection lines
           order: 1
         }
         ```
     - **Axis Scales Configuration:** Ensure Chart.js is initialized with two Y scales (`y` for price, `yVolume` for volume):
       ```javascript
       scales: {
         x: { ... },
         y: { type: 'linear', position: 'left', ticks: { ... } },
         yVolume: {
           type: 'linear',
           position: 'right',
           display: false, // hide the axis scale values
           grid: { display: false },
           // Scale volume so the maximum volume bar only takes up 15-20% of the vertical space
           max: Math.max.apply(null, prices.map(p => p.volume || 0)) * 5
         }
       }
       ```
     - Ensure the Chart tooltip options dynamically map parameters (e.g., showing Open/High/Low/Close and Volume on hover).
---

## 3. Tradeville API Schema Mapping Cheat Sheet

### 1. `Symbol` Command
- **Request:**
  ```json
  { "cmd": "Symbol", "prm": { "symbol": "BRD" } }
  ```
- **Response Structure:**
  ```json
  {
    "cmd": "Symbol",
    "data": {
      "Symbol": ["BRD"],
      "Price": [14.46],
      "RefPrice": [14.8],
      "Bid": [14.44],
      "Ask": [14.46],
      "SharesNr": [696901518],
      "Name": ["BRD - Groupe Societe Generale"]
    }
  }
  ```
- **Mapping:**
  - `price = data["Price"][0]`
  - `ref_price = data["RefPrice"][0]`
  - `change_pct = ((price - ref_price) / ref_price * 100) if ref_price else 0.0`

### 2. `DailyValues` Command
- **Request:**
  ```json
  { "cmd": "DailyValues", "prm": { "symbol": "BRD", "dstart": "1jan19", "dend": null } }
  ```
- **Response Structure:**
  ```json
  {
    "cmd": "DailyValues",
    "data": {
      "Symbol": ["BRD", "BRD", "BRD"],
      "Date": ["2020-11-02", "2020-11-03", "2020-11-04"],
      "Open": [11.42, 11.76, 12.06],
      "Close": [11.72, 12.04, 12.24],
      "Volume": [116600, 71969, 57774]
    }
  }
  ```
- **Mapping:**
  - Loop through indices `0` to `len(data["Date"]) - 1`.
  - Date = `data["Date"][i]`
  - Close price = `data["Close"][i]`
