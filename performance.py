"""
Performance tracker — PostgreSQL version
Survives Railway reboots. Falls back to JSON if no DATABASE_URL.
"""

import os
import json
import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    USE_PG = True
else:
    USE_PG = False
    TRADES_FILE = "paper_trades.json"


def get_conn():
    if USE_PG:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        # Create table if needed
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id SERIAL PRIMARY KEY,
                timestamp TEXT,
                action TEXT,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                size REAL,
                confidence TEXT,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL DEFAULT NULL,
                pnl REAL DEFAULT NULL,
                exit_reason TEXT DEFAULT NULL
            )
        """)
        conn.commit()
        return conn
    return None


# ── JSON fallback helpers ─────────────────────────────────

def load_trades():
    if USE_PG:
        return []  # not used in PG mode
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE) as f:
        return json.load(f)


def save_trades(trades):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)


# ── Main functions ────────────────────────────────────────

def record_trade(action, entry_price, stop_loss, take_profit, size, confidence):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if USE_PG:
        conn = get_conn()
        c    = conn.cursor()
        c.execute("""
            INSERT INTO paper_trades
            (timestamp, action, entry_price, stop_loss, take_profit, size, confidence, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'OPEN')
            RETURNING id
        """, (ts, action, entry_price, stop_loss, take_profit, size, confidence))
        trade_id = c.fetchone()[0]
        conn.commit()
        conn.close()
        print(f"📝 Trade #{trade_id} recorded!")
        return trade_id
    else:
        trades   = load_trades()
        trade_id = len(trades) + 1
        trades.append({
            "id": trade_id, "timestamp": ts,
            "action": action, "entry_price": entry_price,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "size": size, "confidence": confidence,
            "status": "OPEN", "exit_price": None,
            "pnl": None, "exit_reason": None,
        })
        save_trades(trades)
        print(f"📝 Trade #{trade_id} recorded!")
        return trade_id


def update_trade(trade_id, current_price):
    if USE_PG:
        conn = get_conn()
        c    = conn.cursor()
        c.execute("""
            SELECT action, entry_price, stop_loss, take_profit, size, status
            FROM paper_trades WHERE id=%s
        """, (trade_id,))
        row = c.fetchone()
        if not row or row[5] != "OPEN":
            conn.close()
            return False

        action, entry, sl, tp, size, _ = row
        if action == "BUY":
            pnl_pct = (current_price - entry) / entry
            hit_sl  = current_price <= sl
            hit_tp  = current_price >= tp
        else:
            pnl_pct = (entry - current_price) / entry
            hit_sl  = current_price >= sl
            hit_tp  = current_price <= tp

        if hit_sl or hit_tp:
            exit_price  = sl if hit_sl else tp
            exit_reason = "Stop Loss 🛑" if hit_sl else "Take Profit ✅"
            pnl         = size * pnl_pct
            c.execute("""
                UPDATE paper_trades
                SET status='CLOSED', exit_price=%s, exit_reason=%s, pnl=%s
                WHERE id=%s
            """, (exit_price, exit_reason, round(pnl, 2), trade_id))
            conn.commit()
            conn.close()
            return True

        conn.close()
        return False
    else:
        trades  = load_trades()
        updated = False
        for trade in trades:
            if trade["id"] != trade_id or trade["status"] != "OPEN":
                continue
            entry  = trade["entry_price"]
            sl     = trade["stop_loss"]
            tp     = trade["take_profit"]
            size   = trade["size"]
            action = trade["action"]

            if action == "BUY":
                pnl_pct = (current_price - entry) / entry
                hit_sl  = current_price <= sl
                hit_tp  = current_price >= tp
            else:
                pnl_pct = (entry - current_price) / entry
                hit_sl  = current_price >= sl
                hit_tp  = current_price <= tp

            if hit_sl or hit_tp:
                trade["status"]      = "CLOSED"
                trade["exit_price"]  = sl if hit_sl else tp
                trade["exit_reason"] = "Stop Loss 🛑" if hit_sl else "Take Profit ✅"
                trade["pnl"]         = round(size * abs(pnl_pct), 2) * (1 if not hit_sl else -1)
                updated = True

        if updated:
            save_trades(trades)
        return updated


def get_performance_report():
    if USE_PG:
        conn = get_conn()
        c    = conn.cursor()
        c.execute("SELECT * FROM paper_trades ORDER BY id DESC")
        rows    = c.fetchall()
        conn.close()
        cols    = ["id","timestamp","action","entry_price","stop_loss",
                   "take_profit","size","confidence","status","exit_price","pnl","exit_reason"]
        trades  = [dict(zip(cols, r)) for r in rows]
    else:
        trades = load_trades()

    if not trades:
        return "📊 No trades recorded yet."

    closed  = [t for t in trades if t["status"] == "CLOSED"]
    open_t  = [t for t in trades if t["status"] == "OPEN"]
    winners = [t for t in closed if t["pnl"] and t["pnl"] > 0]
    losers  = [t for t in closed if t["pnl"] and t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in closed if t["pnl"])
    win_rate  = len(winners) / len(closed) * 100 if closed else 0
    avg_win   = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
    avg_loss  = sum(t["pnl"] for t in losers)  / len(losers)  if losers  else 0

    report = (
        f"📊 PAPER TRADING PERFORMANCE\n"
        f"{'='*30}\n\n"
        f"💰 Total P&L: ${total_pnl:+.2f}\n"
        f"💼 Capital: $1,000 → ${1000+total_pnl:,.2f}\n\n"
        f"📋 Trades:\n"
        f"- Total: {len(trades)} | Open: {len(open_t)} | Closed: {len(closed)}\n"
        f"- Wins: {len(winners)} ✅ | Losses: {len(losers)} ❌\n"
        f"- Win rate: {win_rate:.1f}%\n\n"
        f"💵 Avg win: ${avg_win:.2f} | Avg loss: ${avg_loss:.2f}\n\n"
        f"📋 Last 5 trades:\n"
    )
    for t in list(reversed(trades))[:5]:
        pnl_str = f"${t['pnl']:+.2f}" if t["pnl"] is not None else "OPEN"
        report += f"• {t['timestamp']} {t['action']} @ ${t['entry_price']:,.0f} → {pnl_str}\n"

    return report


if __name__ == "__main__":
    print(get_performance_report())
