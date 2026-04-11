import json
import os
import datetime

TRADES_FILE = "paper_trades.json"

def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE, "r") as f:
        return json.load(f)

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)

def record_trade(action, entry_price, stop_loss, take_profit, size, confidence):
    """Call this every time a paper trade is placed."""
    trade = {
        "id"          : len(load_trades()) + 1,
        "timestamp"   : datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action"      : action,
        "entry_price" : entry_price,
        "stop_loss"   : stop_loss,
        "take_profit" : take_profit,
        "size"        : size,
        "confidence"  : confidence,
        "status"      : "OPEN",
        "exit_price"  : None,
        "pnl"         : None,
        "exit_reason" : None,
    }
    save_trade(trade)
    print(f"📝 Trade #{trade['id']} recorded!")
    return trade["id"]

def update_trade(trade_id, current_price):
    """Check if open trades hit stop loss or take profit."""
    trades = load_trades()
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

        if hit_sl:
            trade["status"]      = "CLOSED"
            trade["exit_price"]  = sl
            trade["exit_reason"] = "Stop Loss 🛑"
            trade["pnl"]         = round(size * -abs(pnl_pct), 2)
            updated = True

        elif hit_tp:
            trade["status"]      = "CLOSED"
            trade["exit_price"]  = tp
            trade["exit_reason"] = "Take Profit ✅"
            trade["pnl"]         = round(size * abs(pnl_pct), 2)
            updated = True

    if updated:
        with open(TRADES_FILE, "w") as f:
            json.dump(trades, f, indent=2)

    return updated

def get_performance_report():
    """Generate a full performance report."""
    trades = load_trades()

    if not trades:
        return "📊 No trades recorded yet."

    closed  = [t for t in trades if t["status"] == "CLOSED"]
    open_t  = [t for t in trades if t["status"] == "OPEN"]
    winners = [t for t in closed if t["pnl"] and t["pnl"] > 0]
    losers  = [t for t in closed if t["pnl"] and t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in closed if t["pnl"])

    win_rate = len(winners) / len(closed) * 100 if closed else 0
    avg_win  = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["pnl"] for t in losers)  / len(losers)  if losers  else 0

    report = f"""
📊 <b>PAPER TRADING PERFORMANCE</b>
{'='*35}

💰 Total P&L: ${total_pnl:+.2f}
📈 Starting capital: $1,000.00
💼 Current capital: ${1000 + total_pnl:,.2f}

📋 Trade Summary:
- Total trades: {len(trades)}
- Open trades: {len(open_t)}
- Closed trades: {len(closed)}
- Winners: {len(winners)} ✅
- Losers: {len(losers)} ❌
- Win rate: {win_rate:.1f}%

💵 Averages:
- Avg win: ${avg_win:.2f}
- Avg loss: ${avg_loss:.2f}

📋 Last 5 trades:
"""
    for t in trades[-5:]:
        pnl_str = f"${t['pnl']:+.2f}" if t["pnl"] is not None else "OPEN"
        report += f"• {t['timestamp']} {t['action']} @ ${t['entry_price']:,.0f} → {pnl_str}\n"

    return report

# ── TEST ──────────────────────────────────────────────────
if __name__ == "__main__":
    print(get_performance_report())