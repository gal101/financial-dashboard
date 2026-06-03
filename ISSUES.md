# BVB Portfolio Dashboard - Issues & Backlog

This document acts as the local issue tracker for the unified server, SSE streaming, and monitor UI implementation.

---

## Issue #1: Unified HTTP Server & Static File Routing
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** None
*   **User Stories:** User Story 1

### What to build
Unify the two separate port servers into a single Python server running on port `8089`. Update the HTTP handler `DashboardHandler` in `server/server.py` to route and serve static files (HTML, CSS, JS, images, JSON) directly from the repository root directory. Remove the static server from `run.bat` and verify that the dashboard can be fully accessed on port `8089/dashboard.html`.

### Acceptance criteria
- [ ] `DashboardHandler` correctly handles GET requests for files (e.g. `dashboard.html`, `company.html`, `style.css`, `company_profile.js`, `.json` files).
- [ ] Server correctly returns the appropriate MIME content-type headers for `.html`, `.css`, `.js`, `.json`, `.png`, and `.jpg` files.
- [ ] Safe path resolution is implemented to prevent directory traversal attacks (e.g., preventing requests containing `..`).
- [ ] `run.bat` is updated to only start `server/server.py` on port `8089`, and the port `8080` static server is removed.
- [ ] The dashboard and company profile pages load and function correctly when accessing `http://localhost:8089/dashboard.html`.

---

## Issue #2: In-Memory Log Capture & Endpoint
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** Issue #1
*   **User Stories:** User Story 3 (partial)

### What to build
Implement a custom logging handler `MemoryLogHandler` that intercepts log events and stores the last 300 logs in a thread-safe in-memory circular buffer (`collections.deque`). Attach this handler to the Python root logger. Implement a new REST endpoint `GET /api/monitor/logs` that returns the buffered logs as a JSON list.

### Acceptance criteria
- [ ] A custom `logging.Handler` subclass `MemoryLogHandler` is implemented with a thread-safe circular buffer capped at 300 entries.
- [ ] `MemoryLogHandler` is attached to the backend logger in `server/server.py`.
- [ ] A new endpoint `GET /api/monitor/logs` returns the log entries in JSON format.
- [ ] Logging performance and memory footprint remain stable, with no resource leaks.

---

## Issue #3: SSE Event Streaming & Connection Status
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** Issue #2
*   **User Stories:** User Story 3 (partial)

### What to build
Implement the Server-Sent Events (SSE) streaming endpoint `GET /api/monitor/events` in `server/server.py`. The endpoint must support persistent HTTP connections and keep track of active client connections. When a client connects, it should immediately receive the current in-memory log buffer, followed by a live stream of new log records and Tradeville WebSocket connection status events.

### Acceptance criteria
- [ ] A new endpoint `GET /api/monitor/events` serves responses with header `Content-Type: text/event-stream`.
- [ ] The server dumps the buffered logs to the client immediately upon connection.
- [ ] New log records are broadcast to all connected SSE clients in real-time as they occur.
- [ ] SSE connections are handled cleanly: client disconnects do not crash the server or leak file descriptors/sockets.
- [ ] Keep-alive ping events are sent periodically (e.g., every 15-30s) to prevent intermediate proxies/VPNs from closing idle streams.

---

## Issue #4: Real-time Price Streaming over SSE
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** Issue #3
*   **User Stories:** User Story 2

### What to build
Update `TradevilleStreamer` in `server/shared/tradeville_streamer.py` to push incoming live price tick events (`updtype: "CA"`) to all active SSE subscribers. Update the frontend (`dashboard.html` and `company_profile.js`) to establish an SSE connection to `/api/monitor/events` and dynamically update displayed stock prices, daily change percentages, and portfolio KPIs without page reloads or disk polling.

### Acceptance criteria
- [ ] Incoming push price ticks on the backend WebSocket are forwarded instantly to SSE subscribers.
- [ ] The frontend connects to the `/api/monitor/events` SSE stream on load.
- [ ] When a `price` event is received, the frontend updates the price values in the holdings table, watchlist, and header KPI totals.
- [ ] The price change animation or indicator triggers in the UI to give visual feedback of the live tick.

---

## Issue #5: Task Tracker & Hermes Ping API
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** Issue #3
*   **User Stories:** User Story 4

### What to build
Implement a Task Tracker module in `server/server.py` to record the status, start time, end time, and result (Success/Failed) of automated cron jobs. Expose `POST /api/monitor/task-ping` to allow the scripts `portfolio_updater.py` and `company_fetcher.py` to register their status. Broadcast task status changes as `task` events over the SSE stream.

### Acceptance criteria
- [ ] An in-memory or simple SQLite table records the execution status and duration of server tasks.
- [ ] Endpoint `POST /api/monitor/task-ping` accepts task name, state (running/success/failed), and error message.
- [ ] `portfolio_updater.py` and `company_fetcher.py` are modified to invoke the task ping endpoint at the start and completion of their execution.
- [ ] Task status transitions are broadcast in real-time over the SSE stream to all active subscribers.

---

## Issue #6: Server Monitor UI & Control Buttons
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** Issue #3, Issue #5
*   **User Stories:** User Story 3, 5

### What to build
Add a "Monitor" section to the BVB Dashboard (either as a sidebar tab, modal, or dedicated sub-page `monitor.html` served by port 8089). This UI must connect to the `/api/monitor/events` SSE stream to display a live logging terminal, the status of the Tradeville WebSocket, task execution history, and control buttons to manually trigger server actions.

### Acceptance criteria
- [ ] A new Server Monitor UI is accessible from the dashboard interface.
- [ ] A scrollable terminal-like box displays logs streamed in real-time.
- [ ] The WebSocket connection status (Connected, Disconnected, Reconnecting) is displayed.
- [ ] A list shows task states (e.g. Portfolio Sync, Daily History) with their last run times and status.
- [ ] Buttons are wired to trigger actions:
    - `Sync Portfolio` -> Triggers portfolio updater.
    - `Force Reconnect` -> Force-reconnects Tradeville WebSocket.
    - `Trigger History Update` -> Triggers history updates.
    - `Reset Subscriptions` -> Refreshes active subscriptions.

---

## Issue #7: Incremental History Fetching & Watchlist Subscription Cleanup
*   **Type:** AFK
*   **Status:** Completed
*   **Blocked by:** Issue #1
*   **User Stories:** User Story 6, 7

### What to build
Optimize `company_fetcher.py` to fetch historical OHLCV data incrementally. Before querying Tradeville's `DailyValues` command, query the SQLite database for the maximum date existing for that symbol. Set `dstart` to `max_date + 1 day` to fetch only the missing delta (falling back to 5 years if no data exists). Update watchlist deletion to remove the symbol from the active WebSocket subscription list without deleting database rows.

### Acceptance criteria
- [ ] `company_fetcher.py` queries `MAX(date)` from `price_history` for existing symbols and requests only the missing period.
- [ ] New watchlist symbols correctly download the full 5-year history.
- [ ] Deleting a symbol from the watchlist removes it from `watchlist.json` and updates `TradevilleStreamer.active_tickers`.
- [ ] Historical prices and metadata for deleted watchlist symbols remain intact in the SQLite database.
