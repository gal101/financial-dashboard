## Problem Statement

The BVB Financial Dashboard currently relies on Yahoo Finance (`yfinance`) as its source of market prices and price history. However, Yahoo Finance presents several severe limitations for this project:
1. **Unreliability and Rate Limits:** Yahoo Finance requests frequently suffer from rate limits, slow response times, or IP blocks.
2. **Missing Instruments:** Yahoo Finance does not list BVB structural products (such as Turbo Certificates like `EBTLVTL19`), forcing the dashboard to ignore them or use stale reference prices.
3. **Inconsistent Symbol Formats:** Yahoo Finance requires BVB tickers to be suffixed with `.RO` (e.g., `TLV.RO`), which introduces complexity and mapping layers compared to the clean, native BVB tickers used inside the database and portfolio files.
4. **Data Discrepancies:** Key financial figures on Yahoo Finance are often stale or incorrect for Romanian equities.

## Solution

Migrate the market data sourcing from Yahoo Finance to the official Tradeville API. Tradeville is the primary BVB retail broker, offering native access to all BVB instruments (including equities, bonds, and structured products) using clean BVB tickers without suffixes. 

Since the Python backend server runs persistently inside a Docker container (as part of a Docker Compose setup behind Nginx), the migration will combine two patterns:
1. **Persistent WebSocket Streaming (Live):** A background thread/worker (`TradevilleStreamer`) running in the persistent backend container will connect to Tradeville, authenticate once, and subscribe to all active symbols. It will listen for real-time price updates (push notifications) and cache them, enabling instantaneous dashboard refreshes.
2. **On-Demand Requests (Short-Lived):** Short-lived, synchronous connections using a helper client (`TradevilleClient`) will be used to fetch historical chart data (`DailyValues`) on-demand when a user loads a company profile.

## User Stories

1. As a portfolio owner, I want my holdings' current prices to be fetched from Tradeville, so that I have the most accurate and reliable valuation for my BVB shares.
2. As a portfolio owner, I want to track the valuation of my turbo certificates and structural products (like `EBTLVTL19`), so that my total portfolio value is complete and correct.
3. As a watchlist user, I want the watchlist prices to be updated server-side from Tradeville, so that I can see the latest market state without CORS or rate-limit issues.
4. As a dashboard user, I want my company profile charts to load historical price data fetched from Tradeville, so that I can view accurate 5-year price trends.
5. As an administrator, I want a setup script to configure my Tradeville credentials once, so that I don't have to manually edit environment files.
6. As a developer, I want the system to fall back to demo credentials automatically if my custom credentials are not set up, so that the application is immediately runnable after cloning.
7. As a system runner, I want the WebSocket connections to be reused during batch updates (like updating all portfolio holdings at once), so that the update process is fast and doesn't spam login requests.
8. As a persistent server host, I want a background worker to maintain a persistent connection for streaming live quotes, so that my dashboard has access to real-time prices and updates instantaneously without making repeated REST or WebSocket handshakes on every page load.
9. As a system operator, I want to be able to fetch prices and history for a specific single symbol when adding it to my watchlist, so that I don't trigger a slow full update of all symbols and hit API rate limits.
10. As a dashboard viewer, I want to toggle between a standard Close line chart and a Min-Max daily range chart on the company profile, so that I can see the intraday volatility and price trends in the same view.

### 1. Centralized WebSocket Gateway & Streaming Daemon
To prevent rate limit issues (max 20 commands per 10 seconds) and avoid multi-login conflicts, all communication with the Tradeville API is centralized through a single gateway running inside `server.py`:
* **Single WebSocket Connection:** The `TradevilleStreamer` background daemon maintains the *only* active WebSocket connection to Tradeville.
* **Local HTTP Proxy Endpoint:** `server.py` exposes a private internal HTTP endpoint (`POST /api/tradeville/request`). CLI scripts (like `company_fetcher.py` or `portfolio_updater.py`) do not connect to Tradeville directly; they send standard POST requests to this local proxy with their target JSON command payload.
* **Transmitter Queue (Throttling):** The gateway maintains a thread-safe Python `queue.Queue` for outbound requests. A dedicated sender thread pulls requests from this queue and enforces a minimum `0.5s` delay between consecutive API requests.
* **Request-Response Sync:** The local HTTP handler puts the command into the queue along with a `threading.Event`. When the WebSocket receiver thread receives the matching command response from Tradeville, it populates the result and calls `.set()` on the event to instantly unblock and return the HTTP response to the caller.
* **Parallel Worker Thread Pool (Live Push):** Unsolicited push messages (like real-time price updates `updtype: "CA"`) are caught by the receiver thread and immediately dropped into a separate **Processing Queue**. A pool of worker threads (`ThreadPoolExecutor` or dedicated worker threads) processes these messages in parallel (calculating price changes, updating memory cache, and writing to SQLite). This ensures the WebSocket receive buffer is never blocked, even during heavy trading volumes.
* **Autologin & Demo Fallback:** The streaming daemon reads credentials from the environment and falls back to the public demo credentials (`!DemoAPITDV` / `DemoAPITDV` / `demo: true`) automatically.
### 2. Credentials Configuration
We will introduce two interactive setup scripts (`setup_credentials.py` and `setup_credentials.sh`) in the project root:
- They will prompt the user to input `TRADEVILLE_USER`, `TRADEVILLE_PASSWORD`, and `TRADEVILLE_DEMO` (Y/N).
- They will generate a `.env` file containing these variables, which will be loaded via `python-dotenv` or manual parsing inside config files.
- The `.env` file is added to `.gitignore`.

### 3. Symbol Format & Structured Products
- All symbol queries will be done using the exact BVB tickers (e.g., `TLV`, `SNP`, `EBTLVTL19`) without suffixes.
- Filtering out certificates starting with `EBTLV` will be completely removed, allowing active valuation of structured products.

### 4. Date Parameter Formatting & SQLite OHLCV Schema
- We will implement a helper `format_date_to_tradeville` to translate dates to the Tradeville API format: `<day><month_3_letters_english_lowercase><year_2_digits>` (e.g. `2jun21` for `2021-06-02`).
- **SQLite Schema Expansion:** The SQLite `price_history` table will be modified to support full OHLCV by adding `open`, `high`, `low`, and `volume` columns. The Python data access layer (`db.py`) will be updated to insert, query, and export these fields in the JSON payload sent to the frontend.

### 5. Script Modifications & Targeted Queries
* **Targeted CLI Queries:** Both `portfolio_updater.py` and `company_fetcher.py` will be modified to optionally accept specific symbols as CLI arguments (e.g. `python company_fetcher.py TLV`). If arguments are provided, they will only query Tradeville for those specific symbols.
* **`portfolio_updater.py`:** Replaced `yfinance` fetcher with a `TradevilleClient` context block that fetches prices in a loop (using targeted symbols if passed via CLI, else all symbols).
* **`company_fetcher.py`:** Replaced `yfinance.Ticker.history` with `TradevilleClient.get_daily_values`. If specific symbols are passed via CLI, it fetches history and structural metadata (via `Symbol` command) only for those symbols, saving it to SQLite. It will extract and insert the full OHLCV datasets (`open`, `high`, `low`, `volume`, `close`) from Tradeville's `DailyValues` command.
* **`server/handlers/refresh.py` & `watchlist.py`:** Updated to trigger targeted updates (passing the specific symbol to the script subprocesses) when a new company is added to the watchlist.

### 6. Automated Portfolio Sync & Personal Activity Log
* **Automated Portfolio Sync:** `portfolio_updater.py` will be modified to query Tradeville's `Portfolio` command via the local HTTP proxy gateway. If real credentials are used, it will automatically sync holding symbols, quantities, and average buy prices (`AvgPrice`) directly from the Tradeville account, dynamically updating/overwriting the local `bvb_portfolio.json` before calculating valuations.
* **Activity Sync & Realized P/L:** A new sync mechanism (`activity_sync.py` script or server background task) will query the `Activity` command for the account's transaction history. It will populate a new SQLite table `user_transactions` (`date`, `op_type`, `symbol`, `quantity`, `price`, `commission`, `amount`) to track buy/sell logs, calculate realized profits, and log actual dividends received, displaying them in a new UI transaction view.

### 7. Frontend Dual-Chart Toggle & Volume Overlay
* **Toggle UI:** A new button group (`#ch-type-btns`) will be added to `company.html` next to the period buttons, displaying two toggle options: `Linie` (Line Chart) and `Min-Max` (Daily Range Chart).
* **Discrete Volume Overlay:** A separate volume bar dataset (`type: 'bar'`, `data: prices.map(p => p.volume)`) will be added to the chart. It will be mapped to a hidden secondary Y-axis (`yVolume`) scaled so that the volume bars only occupy the bottom 15-20% of the chart area (acting as a discrete, non-overlapping background indicator).
* **Chart Rendering (`company_profile.js`):**
  * **Line Chart:** Rendered using the Close price dataset overlaying the volume bars.
  * **Min-Max Chart:** The daily price range is rendered as a vertical floating bar (`type: 'bar'`, `data: [[low, high]]`) with a very thin `barThickness` (e.g. 2px). The closing price is overlaid as a scatter points dataset (`type: 'line'`, `showLine: false`, `pointRadius: 2`), both overlaying the discrete volume bars.

## Testing Decisions

- **Integration Verification:** A test script `test_tradeville.py` will be created to check connection, login, `Symbol` queries, and `DailyValues` history retrieval.
- **Unit Testing:** Helper logic (such as date formatting `format_date_to_tradeville`) will be written in a modular, pure-functional way to be easily tested.
- **Prior Art:** Since there are no existing unit tests in this repository, `test_tradeville.py` will serve as the initial integration testing harness.

## Out of Scope

* **Order Placement:** Launching or managing orders on Tradeville accounts is completely out of scope. The API is strictly used for reporting and data retrieval.
* **Bi-directional WebSocket between Frontend and Backend:** Implementing WebSockets or Server-Sent Events (SSE) to push prices to the frontend browser dynamically is out of scope. The frontend will still fetch data via HTTP polling/refreshes, but the backend will serve these requests instantly from its background stream cache.
## Further Notes

- In case of network drops or timeout during batch queries, the client should implement retry logic or graceful error recovery (falling back to existing stored prices if Tradeville fails).
- **Server Container Downtime Safety:** When CLI scripts (`portfolio_updater.py`, `company_fetcher.py`) are triggered via cron jobs while the persistent server container is stopped or restarting (resulting in a local connection refusal), they MUST catch the connection exception gracefully, write a clean error log (e.g. `[offline] Local Tradeville Proxy is down. Skipping update.`), and exit with a code `0` (or write safe fallbacks) without crashing or corrupting the SQLite database.