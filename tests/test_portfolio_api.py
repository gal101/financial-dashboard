import unittest
import os
import sqlite3
import json
from datetime import datetime, timezone
import sys

# Add back-end to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "back-end"))

from db import get_db, get_user_db
from handlers.portfolio import handle_get_portfolio, handle_get_transactions
class TestPortfolioAPI(unittest.TestCase):
    def setUp(self):
        self.user_conn = sqlite3.connect(":memory:")
        self.user_conn.row_factory = sqlite3.Row
        self.user_conn.execute("CREATE TABLE portfolio_holdings (symbol TEXT PRIMARY KEY, quantity REAL NOT NULL, avg_price REAL NOT NULL, tip TEXT DEFAULT 'actiuni', updated_at TEXT NOT NULL)")
        self.user_conn.execute("CREATE TABLE user_transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, op_type TEXT NOT NULL, symbol TEXT, quantity REAL, price REAL, commission REAL, amount REAL, profit REAL, obs TEXT)")
        
        self.db_conn = sqlite3.connect(":memory:")
        self.db_conn.row_factory = sqlite3.Row
        self.db_conn.execute("CREATE TABLE companies (symbol TEXT PRIMARY KEY, name TEXT NOT NULL)")
        self.db_conn.execute("CREATE TABLE price_history (symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, PRIMARY KEY(symbol, date))")
        
        # Setup mock public data
        self.db_conn.execute("INSERT INTO companies (symbol, name) VALUES ('SNP', 'OMV Petrom')")
        self.db_conn.execute("INSERT INTO price_history (symbol, date, close) VALUES ('SNP', '2026-06-05', 1.05)")
        
        # Patch the functions in handlers.portfolio
        import handlers.portfolio
        self.orig_get_user_db = handlers.portfolio.get_user_db
        self.orig_get_db = handlers.portfolio.get_db
        handlers.portfolio.get_user_db = lambda: self.user_conn
        handlers.portfolio.get_db = lambda: self.db_conn
        
        # Setup mock user data
        now_str = datetime.now(timezone.utc).isoformat()
        self.user_conn.execute(
            "INSERT INTO portfolio_holdings (symbol, quantity, avg_price, tip, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SNP", 1000, 1.00, "actiuni", now_str)
        )
        
        self.user_conn.execute(
            "INSERT INTO user_transactions (date, op_type, symbol, quantity, price, amount, profit, obs) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-06-01T10:00:00Z", "Sell", "SNP", 1000, 1.05, 1050.0, 50.0, None)
        )
        
        self.user_conn.execute(
            "INSERT INTO user_transactions (date, op_type, symbol, quantity, price, amount, profit, obs) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-06-02T10:00:00Z", "In", "RON", None, None, 50.0, 0.0, "dividend SNP")
        )
        self.db_conn.commit()

    def tearDown(self):
        import handlers.portfolio
        handlers.portfolio.get_user_db = self.orig_get_user_db
        handlers.portfolio.get_db = self.orig_get_db
        self.user_conn.close()
        self.db_conn.close()

    def test_get_portfolio(self):
        res = handle_get_portfolio()
        
        self.assertNotIn("error", res)
        self.assertIn("metadata", res)
        self.assertIn("holdings", res)
        
        holdings = res["holdings"]
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["simbol"], "SNP")
        self.assertEqual(holdings[0]["actiuni"], 1000)
        self.assertEqual(holdings[0]["pret_medie_achizitie_RON"], 1.00)
        self.assertEqual(holdings[0]["pret_actual_RON"], 1.05)
        self.assertEqual(holdings[0]["investitie_initiala_RON"], 1000.0)
        self.assertEqual(holdings[0]["valoare_evaluata_RON"], 1050.0)
        self.assertEqual(holdings[0]["profit_pierdere_RON"], 50.0)
        
        meta = res["metadata"]
        self.assertEqual(meta["total_investit_RON"], 1000.0)
        self.assertEqual(meta["total_evaluare_RON"], 1050.0)
        self.assertEqual(meta["realized_pnl"], 50.0)
        self.assertEqual(meta["dividends"], 50.0)
        self.assertEqual(meta["real_profit_loss"], 150.0)
    def test_get_transactions(self):
        res = handle_get_transactions(limit=10)
        
        self.assertNotIn("error", res)
        self.assertIn("transactions", res)
        
        txs = res["transactions"]
        self.assertEqual(len(txs), 2)
        self.assertEqual(txs[0]["op_type"], "In")
        self.assertEqual(txs[1]["op_type"], "Sell")

if __name__ == "__main__":
    unittest.main()
