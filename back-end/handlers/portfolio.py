import logging
from db import get_db, get_user_db

log = logging.getLogger("server")

def handle_get_portfolio():
    user_conn = get_user_db()
    db_conn = get_db()
    try:
        # 1. Read holdings
        holdings_rows = user_conn.execute("SELECT symbol, quantity, avg_price, tip, updated_at FROM portfolio_holdings").fetchall()
        holdings = []
        open_positions = {}
        for r in holdings_rows:
            holdings.append(dict(r))
            open_positions[r["symbol"]] = {"quantity": r["quantity"], "avg_price": r["avg_price"]}
            
        # 2. Get latest prices from bvb_dashboard.db
        prices = {}
        if holdings:
            symbols = [h["symbol"] for h in holdings]
            placeholders = ",".join(["?"] * len(symbols))
            # Get latest close price for each symbol
            query = f"""
                SELECT p.symbol, p.close, c.name
                FROM price_history p
                LEFT JOIN companies c ON c.symbol = p.symbol
                WHERE p.symbol IN ({placeholders}) 
                AND p.date = (SELECT MAX(date) FROM price_history AS ph WHERE ph.symbol = p.symbol)
            """
            price_rows = db_conn.execute(query, symbols).fetchall()
            for r in price_rows:
                prices[r["symbol"]] = {"close": r["close"], "name": r["name"]}
        # 3. Calculate Unrealized PnL & add current prices to holdings
        unrealized_pnl = 0.0
        total_eval = 0.0
        total_invested = 0.0
        
        enhanced_holdings = []
        for h in holdings:
            sym = h["symbol"]
            qty = h["quantity"]
            avg_price = h["avg_price"]
            current_price = prices.get(sym, {}).get("close", avg_price)
            tip = h.get("tip", "actiuni")
            nume = prices.get(sym, {}).get("name") or sym
            
            invested = qty * avg_price
            eval_val = qty * current_price
            pnl = eval_val - invested
            
            total_invested += invested
            total_eval += eval_val
            unrealized_pnl += pnl
            
            enhanced_holdings.append({
                "tip": tip,
                "nume": nume,
                "simbol": sym,
                "actiuni": qty,
                "pret_medie_achizitie_RON": avg_price,
                "pret_actual_RON": current_price,
                "investitie_initiala_RON": round(invested, 2),
                "valoare_evaluata_RON": round(eval_val, 2),
                "profit_pierdere_RON": round(pnl, 2),
                "variatie_pret_pct": round(((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0, 2)
            })
            
        # 4. Calculate Realized PnL and Dividends from user_transactions
        txs = user_conn.execute("SELECT op_type, profit, amount, obs FROM user_transactions").fetchall()
        
        realized_pnl = 0.0
        dividends = 0.0
        
        for tx in txs:
            op = tx["op_type"].upper()
            profit = tx["profit"] or 0.0
            amount = tx["amount"] or 0.0
            obs = (tx["obs"] or "").lower()
            
            if op == "SELL":
                realized_pnl += profit
                
            if op == "IN" and "dividend" in obs:
                dividends += amount
                        
        total_real_pnl = realized_pnl + dividends + unrealized_pnl
        
        # Sort holdings by value descending
        enhanced_holdings.sort(key=lambda x: x["valoare_evaluata_RON"], reverse=True)
        
        # Add weights
        if total_eval > 0:
            for h in enhanced_holdings:
                h["pondere_portofoliu_pct"] = round((h["valoare_evaluata_RON"] / total_eval) * 100, 2)
        else:
            for h in enhanced_holdings:
                h["pondere_portofoliu_pct"] = 0.0
                
        metadata = {
            "sursa": "Tradeville DB",
            "valuta": "RON",
            "total_investit_RON": round(total_invested, 2),
            "total_evaluare_RON": round(total_eval, 2),
            "total_profit_pierdere_RON": round(unrealized_pnl, 2),
            "return_total_pct": round((unrealized_pnl / total_invested * 100) if total_invested > 0 else 0, 2),
            "realized_pnl": round(realized_pnl, 2),
            "dividends": round(dividends, 2),
            "real_profit_loss": round(total_real_pnl, 2)
        }
        
        return {
            "metadata": metadata,
            "holdings": enhanced_holdings
        }
    except Exception as e:
        log.error(f"Error getting portfolio: {e}")
        return {"error": str(e)}
    finally:
        user_conn.close()
        db_conn.close()

def handle_get_transactions(limit=10):
    user_conn = get_user_db()
    try:
        rows = user_conn.execute("SELECT * FROM user_transactions ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
        return {"transactions": [dict(r) for r in rows]}
    except Exception as e:
        log.error(f"Error getting transactions: {e}")
        return {"error": str(e)}
    finally:
        user_conn.close()
