# Tradeville API Migration — Step-by-Step Handoff Document

This document outlines the step-by-step migration process from Yahoo Finance (`yfinance`) to the Tradeville API. This is prepared for the next agent/developer to execute.

## Instructions for the Implementing Agent

Before writing code, please read and adhere to the following development guidelines:

1. **Apply Test-Driven Development (TDD):** Use the `tdd` skill (red-green-refactor loop) when implementing code. Write tests first, ensure they fail, write the minimal code to make them pass, and then refactor. Apply this especially to helper utilities, client methods, and server endpoints.
2. **Follow GitHub Issue Order:** The migration has been decomposed into 8 vertical tracer bullets on GitHub (Issues **#16** through **#23**). Implement them sequentially in the order of their dependencies (starting with #16).
3. **Utilize Sub-Agents:** You are encouraged to delegate individual issues to specialized sub-agents (e.g., `task` for engineering slices, `oracle` for complex reviews, `designer` for frontend styling).
4. **Respect Dependency-Aware Delegation:** Do NOT spawn sub-agents for blocked tasks. Ensure all blockers for a given issue are fully implemented, verified, and merged before starting or delegating that issue.

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

---

### Step 2: Implement the Centralized Gateway (`TradevilleStreamer`) & Server Proxy
Create `financial-dashboard/server/shared/tradeville_streamer.py` and modify `server.py` to establish a single centralized entry point for all Tradeville requests.

1. **Gateway Class (`TradevilleStreamer(threading.Thread)`):**
   - **Shared Resources:**
     - `self.out_queue = queue.Queue()`: Thread-safe queue for outgoing API commands.
     - `self.pending_requests = {}`: Dictionary mapping `(cmd, symbol)` (e.g. `('Symbol', 'BRD')`) to `{"event": threading.Event(), "response": None}`.
     - `self.push_queue = queue.Queue()`: For incoming push updates (`updtype: "CA"`).
     - `self.worker_pool = ThreadPoolExecutor(max_workers=4)`: Worker pool to process pushes in parallel, ensuring the socket receiver never blocks.
   - **Operation Threads:**
     - **Connection & Login:** Connects to `wss://api.tradeville.ro:443` (protocol `apitv`) using `.env` credentials. Sends `login` command.
     - **Transmitter Loop (Thread):** Pulls from `self.out_queue`. Enforces a strict minimum `0.6s` cooldown between consecutive WebSocket sends to ensure we never exceed the 20 requests per 10 seconds limit. The sleep time is calculated as `max(0, 0.6 - (time.time() - last_sent_time))`.
     - **Receiver Loop (Thread):** Reads from `self.ws.recv()`.
       - If a command response arrives, matches the key in `self.pending_requests`, populates the `"response"` value, and calls `.set()` on the `Event` to wake up the waiting HTTP handler.
       - If a push message arrives (`updtype: "CA"`), drops it into `self.push_queue` immediately.
     - **Push Workers:** Consume from `self.push_queue`, parse price ticks, calculate changes ($\text{volz\_diff} = \text{volz} - \text{old\_volz}$), and update the memory cache and SQLite price history.
     - **Auto-Reconnect:** Implements infinite reconnect loop with exponential backoff. Resubscribes to active tickers on reconnect.
     - **Daily Reset:** Forcibly closes and reconnects the socket daily at 09:40 EEST to refresh session states before market open.

2. **HTTP Proxy Endpoint in `server.py`:**
   - Expose `POST /api/tradeville/request`:
     1. Parse target command payload (e.g., `{ "cmd": "DailyValues", ... }`).
     2. Register a `threading.Event()` in `streamer.pending_requests` under the request key.
     3. Append the command to `streamer.out_queue`.
     4. Block on `Event.wait(timeout=10)`.
     5. **Offline/Timeout Fallback:** If `Event.wait` times out or a connection failure occurs, catch the exception, retrieve the last known cached data from SQLite/local files, and return it with a flag `is_offline: true`.

---

### Step 3: Implement the Shared `TradevilleClient`
Create `financial-dashboard/server/shared/tradeville_client.py` as a lightweight helper for other scripts to query Tradeville via the local server proxy.

* **Class Design:** `class TradevilleClient:`
* **Context Manager Support:** Implement `__enter__(self)` and `__exit__(self, exc_type, exc_val, exc_tb)`.
  - It does NOT connect to Tradeville. It simply initializes a connection session to the local HTTP server.
* **Helper Functions:**
  - `send_request(self, payload: dict) -> dict`: Sends a POST request to `http://localhost:8089/api/tradeville/request` with the payload as JSON, and returns the parsed JSON response.
    - **Offline Safety:** Wrap the POST call in a `try...except requests.exceptions.RequestException` block. If the local proxy server is stopped (e.g. `ConnectionRefusedError` or timeout), log `[offline] Local Tradeville Proxy is down` and return `{"error": "offline"}` or raise a custom `ProxyDownException`.
  - `format_date(self, d: date) -> str`: Converts a Python `date`/`datetime` object into `<day><month_3_letters_english_lowercase><year_2_digits>` (e.g. `2jun21`).
  - `get_symbol_price(self, symbol: str) -> dict`: Calls `self.send_request({ "cmd": "Symbol", "prm": { "symbol": symbol } })`.
  - `get_daily_values(self, symbol: str, start_date: date, end_date: date = None) -> list`: Calls `self.send_request({ "cmd": "DailyValues", "prm": { "symbol": symbol, "dstart": self.format_date(start_date), "dend": self.format_date(end_date) if end_date else None } })`.

---

### Step 4: Implement Verification Script `test_tradeville.py`
Create a test script `test_tradeville.py` in the root directory:
- Use the `TradevilleClient` context manager.
- Fetch current details for `TLV` using `get_symbol_price`.
- Fetch 3 days of historical prices for `BRD` using `get_daily_values`.
- Print outputs to console to verify the local proxy, login, connection, and parser logic work correctly.

---

### Step 5: Update `portfolio_updater.py` with Automated Portfolio Sync
Refactor `portfolio_updater.py` to use `TradevilleClient`:
1. Support targeted updates: Check for specific tickers passed as CLI arguments. If present, only update those tickers; otherwise, update all.
2. **Automated Portfolio Sync:** Query Tradeville's `Portfolio` command via `client.send_request({"cmd": "Portfolio", "prm": {"data": null}})`. If a real account is configured, retrieve the actual portfolio holdings (symbols, quantities, buy prices) and dynamically update/overwrite the local `bvb_portfolio.json` file.
3. Remove `import yfinance as yf` and `yahoo_symbol` mappings.
4. Calculate percentage change relative to Tradeville's reference price:
   $$\text{change\_pct} = \frac{\text{price} - \text{ref\_price}}{\text{ref\_price}} \times 100$$
5. Map this to the portfolio JSON holdings fields: `pret_actual_RON`, `variatie_pret_pct`, `valoare_evaluata_RON`, and `profit_pierdere_RON`.

---

### Step 6: Update `company_fetcher.py` with OHLCV data & Metadata
Refactor `company_fetcher.py` to fetch historical price history and metadata from Tradeville:
1. Support targeted updates: Check for specific tickers passed as CLI arguments. If present, only process those tickers; otherwise, process all.
2. Replace `yf.Ticker(ysym).history(period="5y")` with `client.get_daily_values(sym, start_date=five_years_ago)`.
3. Update `db.py` Schema & Queries: Add `open`, `high`, `low`, and `volume` columns to `price_history` schema. Update `upsert_prices`, `get_company` queries, and `export_to_json` in `db.py` to handle these new fields.
4. Fetch structural metadata: For each target symbol, call `client.get_symbol_price(sym)` to retrieve `SharesNr`, `Earnings`, `EarnDate`, `Name`, and `ISIN`. Upsert these values into the SQLite `companies` and `calculated_metrics` tables.
5. Extract and save raw `open`, `high`, `low`, `volume`, and `close` values directly to the SQLite `price_history` table.

---

### Step 7: Implement Automated Transaction History & Activity Sync
Create `financial-dashboard/server/shared/activity_sync.py` to sync account transactions:
1. Query the `Activity` command: `client.send_request({"cmd": "Activity", "prm": {"symbol": null, "dstart": start_date, "dend": null}})` where `start_date` is the last synced transaction date.
2. Parse each transaction: `Date`, `OpType` (Buy/Sell/In/Out), `Symbol`, `Quantity`, `Price`, `Comission`, `Ammount`.
3. Populate a new SQLite table `user_transactions` (`id`, `date`, `op_type`, `symbol`, `quantity`, `price`, `commission`, `amount`).
4. Calculate realized P/L from sell transactions and store received dividends to automatically display them in a new UI transaction view.

---

### Step 8: Implement Frontend Dual-Chart View (Line ↔ Min-Max Range) and Volume overlay
1. **UI Layout Updates (`company.html`):**
   - Add a toggle button group `#ch-type-btns` next to the `#ch-period-btns` group.
2. **Toggle Javascript Logic (`company_profile.js`):**
   - Define a global state variable `var chartType = 'line';`. Add click listeners to update type and redraw.
3. **Chart Rendering Updates (`renderPriceChart`):**
   - In `company_profile.js`, call `Chart.register(Chart.Filler);` once during script load.
   - In `renderPriceChart()`, compile the datasets dynamically based on `chartType` using the **Shaded Range Band** method:
     * **Volume Dataset (Always present as background overlay):**
       ```javascript
       {
         type: 'bar',
         label: 'Volum',
         data: prices.map(p => p.volume || 0),
         backgroundColor: 'rgba(59, 130, 246, 0.12)', // light blue overlay
         borderColor: 'transparent',
         yAxisID: 'yVolume',
         order: 3
       }
       ```
     * **If `chartType === 'line'`:** Use a single line dataset with `data: prices.map(p => p.close)` (mapped to primary Y-axis `y`, `order: 1`).
     * **If `chartType === 'range'`:** Compile three datasets to build the shaded volatility band:
       1. **Dataset 0 (Low Boundary - Invisible):**
          ```javascript
          {
            type: 'line',
            label: 'Minim',
            data: prices.map(p => p.low !== null ? p.low : p.close),
            borderColor: 'transparent',
            pointRadius: 0,
            fill: false,
            order: 2
          }
          ```
       2. **Dataset 1 (High Boundary - Filled to Low):**
          ```javascript
          {
            type: 'line',
            label: 'Maxim',
            data: prices.map(p => p.high !== null ? p.high : p.close),
            borderColor: 'transparent',
            pointRadius: 0,
            fill: '-1', // references previous dataset (index 0 - Low)
            backgroundColor: 'rgba(139, 143, 163, 0.15)', // Shaded range band
            order: 1
          }
          ```
       3. **Dataset 2 (Close Price Line):**
          ```javascript
          {
            type: 'line',
            label: 'Preț Închidere',
            data: prices.map(p => p.close),
            borderColor: color,
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1,
            order: 0
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
           display: false,
           grid: { display: false },
           max: Math.max.apply(null, prices.map(p => p.volume || 0)) * 5 // bottom 20% overlay
         }
       }
       ```
     - **Tooltip Customization:** Leverage Chart.js's built-in `mode: 'index', intersect: false` interaction. Customize the tooltip callbacks to display Open/High/Low/Close cleanly when hovering:
       ```javascript
       plugins: {
         tooltip: {
           callbacks: {
             label: function(ctx) {
               return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(4) + ' RON';
             }
           }
         }
       }
       ```
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
