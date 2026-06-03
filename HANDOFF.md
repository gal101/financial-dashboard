# Handoff: BVB Financial Dashboard — Performance Issues

## Context

The dashboard was migrated to a unified server architecture (ThreadingHTTPServer on port 8089) with SSE live price streaming, Server Monitor, dynamic JSON overlay, and singleton server protection. All 11 tests pass. Full details in the commit history and `ISSUES.md`.

## Problem

**Navigating between the Dashboard and Company Profile pages causes 10-15 second loading delays.** This affects all companies, not just newly added ones (like the ETF `TVBETETF`). The more the user switches between pages, the slower it gets.

## Root Cause Analysis

### 1. Massive Static File Re-Downloads (Primary Suspect)
- `company_data.json` is **~2.2 MB** (92,614 lines) containing full price history (1200+ rows per company), quarterly/annual financials, BVC data, calendars, and metrics for every company.
- **Every page load** (Dashboard or Profile) fetches this file fresh — the server doesn't set any `Cache-Control` headers.
- Navigating Dashboard → Profile → Dashboard means 3 × 2.2 MB = **6.6 MB** downloaded in quick succession.
- The `_serve_static_file` method in `server.py` sends `Content-Type` and `Content-Length` but **no caching headers**.

### 2. SSE Connection Accumulation (Secondary Suspect)
- Both `dashboard.html` and `company.html` open `EventSource('/api/monitor/events')` connections.
- Each navigation creates a new SSE connection. Old ones should close, but server-side threads may linger until the 15-second `q.get()` timeout expires.
- Rapid navigation could accumulate stale SSE threads holding server resources.

## Proposed Fixes (in priority order)

### Fix 1: Add HTTP Caching Headers (High Impact, Low Effort)
In `server.py` `_serve_static_file()`, add `Cache-Control` header for static assets:
- JSON files (`company_data.json`, `bvb_portfolio.json`, etc.): `max-age=60` (cache 1 minute)
- CSS/JS files: `max-age=3600` (cache 1 hour)
- HTML files: `no-cache` (always validate)

This alone would eliminate repeated 2.2 MB downloads during navigation.

### Fix 2: Limit `/company` API Response Size
The `GET /company?symbol=SYMBOL` fallback endpoint returns ALL `price_history` rows (1200+ per company). For a fallback that's only used when a symbol is missing from `company_data.json`, consider:
- Limiting price_history to last 90 days in the API response
- Or omitting price_history entirely (the page can show "Istoricul de preț se încarcă..." until the static file is regenerated)

### Fix 3: SSE Cleanup on Page Unload
Add a `beforeunload` handler in both `dashboard.html` and `company.html` to explicitly close the EventSource:
```javascript
window.addEventListener('beforeunload', function() {
  if (es) es.close();
});
```

## Recent Fixes Already Applied (for context)
- `company_fetcher.py` now calls `export_to_json()` after history sync
- `watchlist.py` uses `shared.config.streamer` (not `import server.server`)
- New watchlist symbols are initialized in `watchlist_data.json` disk cache and dynamic JSON overlay
- `company_profile.js` has live database API fallback via `GET /company?symbol=SYMBOL`
- Multi-year returns correctly use `data[0]` (first charted point in period)

## Suggested Skills for Next Session
- `diagnose` — to verify the caching fix actually resolves the 10-15s delay
- `tdd` — if new tests are needed for caching headers
