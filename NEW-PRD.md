## Problem Statement

The BVB Financial Dashboard currently operates with two separate server processes (a static file server on port 8080 and an API/WebSocket proxy server on port 8089) and relies on external cron jobs that do not report their status back to the user. This architecture has several limitations:
1. **Complexity:** Running and maintaining two separate ports causes CORS complications and developer overhead (managing multiple terminal windows/containers).
2. **Lack of Real-Time Updates:** The frontend does not receive real-time updates. It must poll static files or trigger manual refreshes, creating lag and unnecessary disk writes.
3. **Black-Box Automation:** Cron jobs (triggered via Hermes) execute silently. If a job fails or runs slow, the user has no visibility unless they check container logs.
4. **Inefficient API Usage:** The daily history updater fetches the entire 5-year OHLCV dataset for every symbol on every run, leading to high latency and redundant API usage.
5. **No Centralized Control:** There is no UI-based admin interface to monitor server health, view live log output, or manually trigger maintenance tasks (like force-reconnecting the WebSocket or syncing portfolio holdings).

## Solution

We will unificate the backend and frontend into a single Python server on port 8089, introduce a real-time event streaming layer using Server-Sent Events (SSE), optimize the database updates to be incremental, and build a dedicated Server Monitor page inside the dashboard. Tailscale will remain the secure entrypoint for private user access, eliminating the need for public domain exposure.

## User Stories

1. As a dashboard viewer, I want to access both the web pages and the API from a single port (8089), so that I don't have to manage CORS issues or multiple server processes.
2. As a dashboard viewer, I want to see price updates, market depth, and portfolio valuations change on my screen in real-time, so that I can monitor BVB sessions dynamically without clicking manual refresh.
3. As a server administrator, I want a dedicated Server Monitor panel in the dashboard, so that I can see the server status, live logs, and background tasks in one place.
4. As a server administrator, I want to see the execution history and status of automated cron jobs (Hermes pings), so that I know if the daily updates succeeded or failed.
5. As a server administrator, I want buttons in the monitor panel to manually trigger a portfolio sync, force a WebSocket reconnection, or run a database update, so that I can control the system without SSH-ing into the server.
6. As a system operator, I want the server to only fetch the missing price history (incremental fetch) since the last recorded date for existing companies, so that database updates are extremely fast and consume minimal API quota.
7. As a watchlist user, I want the system to keep historical data in the database when I remove a symbol from my watchlist, so that if I add it back later or have past transactions with it, the history is immediately available.

## Implementation Decisions

### 1. Unified Python HTTP Server
*   Modify `DashboardHandler` in `server/server.py` to route and serve static files (HTML, CSS, JS, images, JSON) directly from the repository root.
*   Implement secure file serving with MIME-type mapping (`.html` -> `text/html`, `.css` -> `text/css`, `.js` -> `application/javascript`, `.json` -> `application/json`, etc.) and directory traversal protection.
*   Decommission the second static server (port 8080) from `run.bat` and all configurations.

### 2. Server-Sent Events (SSE) Streaming Layer
*   Add a new SSE endpoint `/api/monitor/events` in the HTTP server.
*   Establish persistent connections from the browser. The server will stream live events formatted as `data: { ... }` with the following event types:
    *   `price`: Live price tick updates (`updtype: "CA"`) received from Tradeville WebSocket.
    *   `log`: Live stdout/stderr log entries.
    *   `task`: Cron job/task start, completion, and failure events.
    *   `status`: Tradeville WebSocket connection and API rate-limiting queue status.
*   Update `TradevilleStreamer` to push incoming live ticks to all active SSE subscribers in addition to writing them to the SQLite database.

### 3. In-Memory Logging & Broadcasting
*   Implement a custom `MemoryLogHandler(logging.Handler)` that stores the last 300 logs in a `collections.deque` (in-memory circular buffer).
*   Attach this handler to the root logger in `server.py`.
*   When a client connects to the SSE stream, dump the buffered logs immediately, then stream new logs as they are generated.

### 4. Server Monitor Panel
*   Add a "Monitor" tab or modal in `dashboard.html` (or create a dedicated `monitor.html` accessible from the sidebar).
*   The monitor UI will feature:
    *   **WebSocket Status:** Connection state (Connected, Disconnected, Reconnecting) and latency.
    *   **Live Logging:** A scrollable terminal-style box showing the live log stream.
    *   **Task/Cron Tracker:** A list of automated tasks (Portfolio Sync, Metadata Update, Daily History) showing the last run time, execution duration, and outcome.
    *   **Control Buttons:** 
        *   `Sync Portfolio` -> Calls the internal portfolio update task.
        *   `Force Reconnect` -> Triggers `streamer.force_reconnect()`.
        *   `Trigger History Update` -> Triggers the incremental history sync.
        *   `Reset Subscriptions` -> Refreshes active WebSocket subscriptions.

### 5. Incremental History Fetching
*   Modify `company_fetcher.py` to optimize daily historical updates.
*   Before requesting daily values, query the SQLite `price_history` table for `MAX(date)` for the target ticker.
*   If a record exists, set the Tradeville request `dstart` to `max_date + 1 day`.
*   If no record exists, default to fetching the full 5-year history.

### 6. Scheduled Task Tracker (Ping-back API)
*   Add `POST /api/monitor/task-ping` to `server.py` to register task status updates.
*   Update `portfolio_updater.py` and `company_fetcher.py` to send a start ping and end ping (with success/error details) when they run via Hermes cron.

### 7. Watchlist Deletion
*   When deleting a symbol from the watchlist, only remove it from `watchlist.json`. Do **not** delete any historical price rows or metadata from the SQLite tables.
*   Dynamically remove the deleted symbol from `TradevilleStreamer.active_tickers` so we no longer stream live ticks for it.

## Testing Decisions

*   **SSE Testing:** Verify that multiple browser tabs can establish concurrent SSE connections without leaking file descriptors or blocking the main HTTP event loop.
*   **Logging Capture:** Write unit checks to ensure the `MemoryLogHandler` does not overflow or leak memory, and correctly filters log levels before broadcasting.
*   **Incremental Fetch Validation:** Test `company_fetcher.py` on a symbol with existing history to confirm it only requests the delta, and on a new symbol to confirm it fetches the full 5-year range.

## Out of Scope

*   **Public Authentication:** Adding secure login pages, cookies, or OAuth is out of scope. Tailscale is the designated VPN tool for access control.
*   **Trade Execution:** Initiating trades or managing order books remains out of scope.

## Further Notes

*   Ensure the SSE stream handles browser disconnections cleanly without throwing unhandled socket exceptions on the server.
