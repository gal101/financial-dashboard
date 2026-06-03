"""
Shared configuration for the BVB Dashboard server.
Paths, constants, and secrets.
"""

import os

# Base directory
BASE_DIR = os.environ.get("BASE_DIR")
if not BASE_DIR:
    local_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.exists(os.path.join(local_dir, "bvb_portfolio.json")) or os.path.exists(os.path.join(local_dir, "bvb_portfolio.example.json")):
        BASE_DIR = local_dir
    else:
        BASE_DIR = "/financial-dashboard"

# Data files
PORTFOLIO_FILE = os.path.join(BASE_DIR, "bvb_portfolio.json")
WATCHLIST_FILE = os.path.join(BASE_DIR, "watchlist.json")
WATCHLIST_DATA_FILE = os.path.join(BASE_DIR, "watchlist_data.json")
COMPANY_DATA_FILE = os.path.join(BASE_DIR, "company_data.json")
PENDING_SCRAPES_FILE = os.path.join(BASE_DIR, "pending_scrapes.json")
SCRAPE_RESULTS_DIR = os.path.join(BASE_DIR, "scrape_results")

# Server
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8089

# Hermes webhook
WEBHOOK_URL = "http://localhost:8644/webhooks/scrape"
WEBHOOK_SECRET = b"fH7P_B1XlBSRoeHoIZW2nCj_PJovaX444h3P43SItGY"

# Python (use current interpreter — works in both Hermes container and standalone)
VENV_PYTHON = "/opt/data/.venv/bin/python3"  # fallback for Hermes container
# Always prefer sys.executable if it exists (handles standalone containers)
import sys as _sys
PYTHON_BIN = _sys.executable

# Scripts
UPDATER_SCRIPT = os.path.join(BASE_DIR, "portfolio_updater.py")

# Metrics we consider "required" for a company profile
REQUIRED_METRICS = [
    "marketCap", "trailingPE", "forwardPE", "priceToBook",
    "dividendYield", "dividendRate", "profitMargins",
    "returnOnEquity", "returnOnAssets", "beta",
    "revenueGrowth", "earningsGrowth", "debtToEquity",
    "priceToSalesTrailing12Months", "freeCashflow",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "operatingMargins"
]
