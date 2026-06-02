"""
BVB Dashboard — SQLite database access layer.

🔒 GREEN ZONE (company_fetcher.py can write):
   - price_history

🔴 RED ZONE (read-only for scripts, written by scraping/curation):
   - companies, quarterly, annual, bvc, calendar, calculated_metrics

   market_cap is NOT stored — it's calculated as shares_outstanding × last close.
"""

import sqlite3
import os
import json
import math
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bvb_dashboard.db")


def get_db() -> sqlite3.Connection:
    """Get a connection to the database with WAL mode and foreign keys on."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─── Schema ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    shares_outstanding INTEGER,
    market_cap REAL,
    isin TEXT,
    earnings REAL,
    earn_date TEXT,
    dividend REAL,
    div_price REAL,
    ref_price REAL
);

CREATE TABLE IF NOT EXISTS quarterly (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    revenue REAL,
    net_income REAL,
    source TEXT,
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES companies(symbol)
);

CREATE TABLE IF NOT EXISTS annual (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    revenue REAL,
    net_income REAL,
    source TEXT,
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES companies(symbol)
);

CREATE TABLE IF NOT EXISTS bvc (
    symbol TEXT NOT NULL,
    year INTEGER NOT NULL,
    revenue REAL,
    net_income REAL,
    source TEXT,
    PRIMARY KEY (symbol, year),
    FOREIGN KEY (symbol) REFERENCES companies(symbol)
);

CREATE TABLE IF NOT EXISTS calendar (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    event TEXT NOT NULL,
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES companies(symbol)
);

CREATE TABLE IF NOT EXISTS calculated_metrics (
    symbol TEXT PRIMARY KEY,
    trailing_pe REAL,
    forward_pe REAL,
    eps REAL,
    profit_margin REAL,
    price_to_book REAL,
    dividend_yield REAL,
    updated_at TEXT,
    FOREIGN KEY (symbol) REFERENCES companies(symbol)
);

CREATE TABLE IF NOT EXISTS price_history (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    volume INTEGER,
    value REAL,
    PRIMARY KEY (symbol, date),
    FOREIGN KEY (symbol) REFERENCES companies(symbol)
);

CREATE TABLE IF NOT EXISTS user_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    op_type TEXT NOT NULL,
    symbol TEXT,
    quantity REAL,
    price REAL,
    commission REAL,
    amount REAL
);
"""


def init_db(conn: sqlite3.Connection = None) -> sqlite3.Connection:
    """Initialize database schema. Creates tables if they don't exist."""
    own_conn = conn is None
    if own_conn:
        conn = get_db()
    conn.executescript(SCHEMA)
    # Check and migrate companies table columns
    cursor = conn.execute("PRAGMA table_info(companies)")
    comp_cols = [row["name"] for row in cursor.fetchall()]
    if comp_cols:
        if "isin" not in comp_cols:
            conn.execute("ALTER TABLE companies ADD COLUMN isin TEXT")
        if "earnings" not in comp_cols:
            conn.execute("ALTER TABLE companies ADD COLUMN earnings REAL")
        if "earn_date" not in comp_cols:
            conn.execute("ALTER TABLE companies ADD COLUMN earn_date TEXT")
        if "dividend" not in comp_cols:
            conn.execute("ALTER TABLE companies ADD COLUMN dividend REAL")
        if "div_price" not in comp_cols:
            conn.execute("ALTER TABLE companies ADD COLUMN div_price REAL")
        if "ref_price" not in comp_cols:
            conn.execute("ALTER TABLE companies ADD COLUMN ref_price REAL")
    # Check and migrate price_history table columns
    cursor = conn.execute("PRAGMA table_info(price_history)")
    columns = [row["name"] for row in cursor.fetchall()]
    if columns and "open" not in columns:
        conn.execute("ALTER TABLE price_history ADD COLUMN open REAL")
        conn.execute("ALTER TABLE price_history ADD COLUMN high REAL")
        conn.execute("ALTER TABLE price_history ADD COLUMN low REAL")
        conn.execute("ALTER TABLE price_history ADD COLUMN volume INTEGER")
    if columns and "value" not in columns:
        conn.execute("ALTER TABLE price_history ADD COLUMN value REAL")
    return conn


# ─── Queries ──────────────────────────────────────────────────────────────────

def get_company(conn: sqlite3.Connection, symbol: str) -> dict:
    """Get full company profile with all related data."""
    row = conn.execute("SELECT * FROM companies WHERE symbol = ?", (symbol,)).fetchone()
    if not row:
        return None
    
    result = dict(row)
    
    # Quarterly
    qs = conn.execute(
        "SELECT date, revenue, net_income, source FROM quarterly WHERE symbol = ? ORDER BY date",
        (symbol,)
    ).fetchall()
    result["quarterly"] = [dict(r) for r in qs]
    
    # Annual
    ann = conn.execute(
        "SELECT date, revenue, net_income, source FROM annual WHERE symbol = ? ORDER BY date",
        (symbol,)
    ).fetchall()
    result["annual"] = [dict(r) for r in ann]
    
    # BVC
    bvc = conn.execute(
        "SELECT year, revenue, net_income, source FROM bvc WHERE symbol = ?",
        (symbol,)
    ).fetchone()
    result["bvc"] = dict(bvc) if bvc else None
    
    # Calendar
    cal = conn.execute(
        "SELECT date, event FROM calendar WHERE symbol = ? ORDER BY date",
        (symbol,)
    ).fetchall()
    result["calendar"] = [dict(r) for r in cal]
    
    # Metrics
    metrics = conn.execute(
        "SELECT * FROM calculated_metrics WHERE symbol = ?",
        (symbol,)
    ).fetchone()
    result["metrics"] = dict(metrics) if metrics else {}
    
    # Price history
    prices = conn.execute(
        "SELECT date, close, open, high, low, volume, value FROM price_history WHERE symbol = ? ORDER BY date",
        (symbol,)
    ).fetchall()
    result["price_history"] = [dict(r) for r in prices]
    
    return result


def list_companies(conn: sqlite3.Connection) -> list:
    """List all company symbols."""
    return [r["symbol"] for r in conn.execute("SELECT symbol FROM companies ORDER BY symbol").fetchall()]


# ─── Write helpers ────────────────────────────────────────────────────────────

def sanitize_val(val):
    """Replace NaN/Inf with None for SQLite storage."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def upsert_prices(conn: sqlite3.Connection, symbol: str, prices: list) -> int:
    """Upsert price_history rows — inserts new or updates existing. Returns count."""
    count = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        for p in prices:
            close = sanitize_val(p.get("close"))
            if close is None:
                continue
            open_val = sanitize_val(p.get("open"))
            high = sanitize_val(p.get("high"))
            low = sanitize_val(p.get("low"))
            volume = sanitize_val(p.get("volume"))
            conn.execute(
                "INSERT INTO price_history (symbol, date, close, open, high, low, volume, value) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol, date) DO UPDATE SET "
                "close = excluded.close, "
                "open = COALESCE(excluded.open, open), "
                "high = COALESCE(excluded.high, high), "
                "low = COALESCE(excluded.low, low), "
                "volume = COALESCE(excluded.volume, volume), "
                "value = COALESCE(excluded.value, value)",
                (symbol, p["date"], close, open_val, high, low, volume, sanitize_val(p.get("value")))
            )
            count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return count


def update_market_cap(conn: sqlite3.Connection, symbol: str, market_cap: float):
    """Update market_cap for a company (green zone safe write)."""
    conn.execute(
        "UPDATE companies SET market_cap = ? WHERE symbol = ?",
        (sanitize_val(market_cap), symbol)
    )


def upsert_company(conn: sqlite3.Connection, symbol: str, name: str,
                   sector: str = None, industry: str = None,
                   shares_outstanding: int = None, market_cap: float = None,
                   isin: str = None, earnings: float = None, earn_date: str = None,
                   dividend: float = None, div_price: float = None, ref_price: float = None):
    """Insert or update a company row."""
    conn.execute("""
        INSERT INTO companies (symbol, name, sector, industry, shares_outstanding, market_cap, isin, earnings, earn_date, dividend, div_price, ref_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            name = COALESCE(excluded.name, name),
            sector = COALESCE(excluded.sector, sector),
            industry = COALESCE(excluded.industry, industry),
            shares_outstanding = COALESCE(excluded.shares_outstanding, shares_outstanding),
            market_cap = COALESCE(excluded.market_cap, market_cap),
            isin = COALESCE(excluded.isin, isin),
            earnings = COALESCE(excluded.earnings, earnings),
            earn_date = COALESCE(excluded.earn_date, earn_date),
            dividend = COALESCE(excluded.dividend, dividend),
            div_price = COALESCE(excluded.div_price, div_price),
            ref_price = COALESCE(excluded.ref_price, ref_price)
    """, (symbol, name, sector, industry, shares_outstanding, sanitize_val(market_cap), isin, sanitize_val(earnings), earn_date, sanitize_val(dividend), sanitize_val(div_price), sanitize_val(ref_price)))


def upsert_quarterly(conn: sqlite3.Connection, symbol: str, entries: list):
    """Insert or replace quarterly entries."""
    for e in entries:
        conn.execute("""
            INSERT OR REPLACE INTO quarterly (symbol, date, revenue, net_income, source)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, e["date"], sanitize_val(e.get("revenue")),
              sanitize_val(e.get("net_income")), e.get("source")))


def upsert_annual(conn: sqlite3.Connection, symbol: str, entries: list):
    """Insert or replace annual entries."""
    for e in entries:
        conn.execute("""
            INSERT OR REPLACE INTO annual (symbol, date, revenue, net_income, source)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, e["date"], sanitize_val(e.get("revenue")),
              sanitize_val(e.get("net_income")), e.get("source")))


def upsert_bvc(conn: sqlite3.Connection, symbol: str, bvc_data: dict):
    """Insert or update BVC data."""
    if not bvc_data or not bvc_data.get("revenue"):
        return
    conn.execute("""
        INSERT OR REPLACE INTO bvc (symbol, year, revenue, net_income, source)
        VALUES (?, ?, ?, ?, ?)
    """, (symbol, bvc_data.get("year", 2026),
          sanitize_val(bvc_data["revenue"]),
          sanitize_val(bvc_data.get("net_income")),
          bvc_data.get("source")))


def upsert_calendar(conn: sqlite3.Connection, symbol: str, events: list):
    """Insert or replace calendar events."""
    conn.execute("DELETE FROM calendar WHERE symbol = ?", (symbol,))
    for ev in events:
        conn.execute(
            "INSERT OR IGNORE INTO calendar (symbol, date, event) VALUES (?, ?, ?)",
            (symbol, ev["date"], ev["event"])
        )


def upsert_metrics(conn: sqlite3.Connection, symbol: str, metrics: dict):
    """Insert or update calculated metrics."""
    conn.execute("""
        INSERT OR REPLACE INTO calculated_metrics
        (symbol, trailing_pe, forward_pe, eps, profit_margin, price_to_book, dividend_yield, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol,
          metrics.get("trailing_pe"),
          metrics.get("forward_pe"),
          metrics.get("eps"),
          metrics.get("profit_margin"),
          metrics.get("price_to_book"),
          metrics.get("dividend_yield"),
          datetime.now(timezone.utc).isoformat()))


# ─── Export ──────────────────────────────────────────────────────────────────

def _sanitize_recursive(obj):
    """Recursively replace NaN/Inf with None."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_recursive(v) for v in obj]
    return obj


def export_to_json(output_path: str = None) -> str:
    """
    Export the full database to a JSON file compatible with the frontend.

    This is a READ-ONLY export. The output format matches what
    company_profile.js expects from company_data.json.
    """
    conn = get_db()
    output_path = output_path or os.path.join(os.path.dirname(DB_PATH), "company_data.json")

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "companies": {},
    }

    for symbol in list_companies(conn):
        comp = get_company(conn, symbol)
        if not comp:
            continue

        metrics = comp.get("metrics", {})
        entry = {
            "simbol": symbol,
            "nume": comp["name"],
            "metrics": {
                "sector": comp.get("sector"),
                "industry": comp.get("industry"),
                "marketCap": comp.get("market_cap"),
                "sharesOutstanding": comp.get("shares_outstanding"),
                "isin": comp.get("isin"),
                "earnings": comp.get("earnings"),
                "earnDate": comp.get("earn_date"),
                "dividend": comp.get("dividend"),
                "divPrice": comp.get("div_price"),
                "refPrice": comp.get("ref_price"),
                "forwardPE": metrics.get("forward_pe"),
                "eps": metrics.get("eps"),
                "profitMargins": metrics.get("profit_margin"),
                "priceToBook": metrics.get("price_to_book"),
                "dividendYield": metrics.get("dividend_yield"),
            },
            "quarterly": [
                {
                    "date": f"{q['date']}T00:00:00",
                    "items": {
                        "Total Revenue": q.get("revenue"),
                        "Net Income": q.get("net_income"),
                    },
                    "_note": q.get("source"),
                }
                for q in comp.get("quarterly", [])
            ],
            "annual": [
                {
                    "date": f"{a['date']}T00:00:00",
                    "items": {
                        "Total Revenue": a.get("revenue"),
                        "Net Income": a.get("net_income"),
                    },
                    "_note": a.get("source"),
                }
                for a in comp.get("annual", [])
            ],
            "price_history": [
                {
                    "date": p["date"],
                    "close": p["close"],
                    "open": p.get("open"),
                    "high": p.get("high"),
                    "low": p.get("low"),
                    "volume": p.get("volume"),
                    "value": p.get("value")
                }
                for p in comp.get("price_history", [])
            ],
            "calendar": comp.get("calendar", []),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # BVC
        if comp.get("bvc"):
            entry["bvc"] = {
                "year": comp["bvc"]["year"],
                "revenue": comp["bvc"]["revenue"],
                "net_income": comp["bvc"]["net_income"],
                "source": comp["bvc"].get("source"),
            }

        # Remove None values from metrics
        entry["metrics"] = {k: v for k, v in entry["metrics"].items() if v is not None}

        result["companies"][symbol] = entry

    conn.close()

    # Sanitize and write
    clean = _sanitize_recursive(result)
    json_str = json.dumps(clean, ensure_ascii=False, indent=2, default=str)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    return output_path


# ─── Backup ───────────────────────────────────────────────────────────────────

def backup(conn: sqlite3.Connection = None):
    """Create a timestamped backup of the database."""
    own_conn = conn is None
    if own_conn:
        conn = get_db()

    backup_dir = os.path.join(os.path.dirname(DB_PATH), "db_backups")
    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"bvb_dashboard_{ts}.db")

    bkp = sqlite3.connect(backup_path)
    conn.backup(bkp)
    bkp.close()

    if own_conn:
        conn.close()

    return backup_path


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "backup":
        path = backup()
        print(f"Backup: {path}")
    else:
        conn = init_db()
        symbols = list_companies(conn)
        print(f"Database: {DB_PATH}")
        print(f"Companies: {len(symbols)} — {', '.join(symbols)}")
        conn.close()
