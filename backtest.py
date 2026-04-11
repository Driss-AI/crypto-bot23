import ccxt
import pandas as pd
import pandas_ta as ta
import datetime

# ── SETTINGS ─────────────────────────────────────────────
STARTING_CAPITAL = 1000
RISK_PER_TRADE   = 0.02
STOP_LOSS_PCT    = 0.03
TAKE_PROFIT_PCT  = 0.06
SYMBOL           = "BTC/USDT"
TIMEFRAME        = "1h"
MONTHS_BACK      = 6

# ── FETCH HISTORICAL DATA ────────────────────────────────
def fetch_historical_data():
    print("📡 Fetching 6 months of BTC historical data from Binance...")
    exchange = ccxt.binance()

    since = exchange.parse8601(
        (datetime.datetime.now() - datetime.timedelta(days=MONTHS_BACK * 30))
        .strftime("%Y-%m-%dT%H:%M:%S")
    )

    all_candles = []
    while True:
        candles = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, since=since, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
        if len(candles) < 1000:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    print(f"✅ Got {len(df)} candles from {df['time'].iloc[0].strftime('%Y-%m-%d')} to {df['time'].iloc[-1].strftime('%Y-%m-%d')}")
    return df

# ── CALCULATE INDICATORS ─────────────────────────────────
def add_indicators(df):
    print("📊 Calculating indicators...")
    df["rsi"] = ta.rsi(df["close"], length=14)

    macd = ta.macd(df["close"])
    df["macd"]        = macd.iloc[:, 0]
    df["macd_signal"] = macd.iloc[:, 1]

    bb = ta.bbands(df["close"], length=20)
    df["bb_upper"] = bb.iloc[:, 0]
    df["bb_lower"] = bb.iloc[:, 1]
    df["bb_mid"]   = bb.iloc[:, 2]

    df["volume_avg"] = df["volume"].rolling(20).mean()
    return df.dropna()

# ── TRADING SIGNAL ───────────────────────────────────────
def get_signal(row):
    rsi      = row["rsi"]
    price    = row["close"]
    bb_upper = row["bb_upper"]
    bb_lower = row["bb_lower"]
    macd     = row["macd"]
    macd_sig = row["macd_signal"]
    volume   = row["volume"]
    vol_avg  = row["volume_avg"]

    if (rsi < 32 and
            price <= bb_lower * 1.01 and
            macd > macd_sig and
            volume > vol_avg):
        return "BUY"

    elif (rsi > 68 and
            price >= bb_upper * 0.99 and
            macd < macd_sig and
            volume > vol_avg):
        return "SELL"

    return "HOLD"

# ── RUN BACKTEST ─────────────────────────────────────────
def run_backtest(df):
    print("🔄 Running backtest...\n")

    capital      = STARTING_CAPITAL
    position     = None
    trades       = []
    equity_curve = [capital]

    for i, row in df.iterrows():
        price  = row["close"]
        signal = get_signal(row)

        if position:
            entry     = position["entry_price"]
            direction = position["direction"]

            if direction == "BUY":
                pnl_pct = (price - entry) / entry
            else:
                pnl_pct = (entry - price) / entry

            if pnl_pct <= -STOP_LOSS_PCT:
                pnl = position["size"] * pnl_pct
                capital += position["size"] + pnl
                trades.append({
                    "entry_time"  : position["entry_time"],
                    "exit_time"   : row["time"],
                    "direction"   : direction,
                    "entry_price" : entry,
                    "exit_price"  : price,
                    "pnl"         : round(pnl, 2),
                    "exit_reason" : "Stop Loss 🛑"
                })
                position = None

            elif pnl_pct >= TAKE_PROFIT_PCT:
                pnl = position["size"] * pnl_pct
                capital += position["size"] + pnl
                trades.append({
                    "entry_time"  : position["entry_time"],
                    "exit_time"   : row["time"],
                    "direction"   : direction,
                    "entry_price" : entry,
                    "exit_price"  : price,
                    "pnl"         : round(pnl, 2),
                    "exit_reason" : "Take Profit ✅"
                })
                position = None

        if not position and signal in ["BUY", "SELL"]:
            size     = capital * RISK_PER_TRADE
            capital -= size
            position = {
                "direction"   : signal,
                "entry_price" : price,
                "entry_time"  : row["time"],
                "size"        : size,
            }

        equity_curve.append(capital + (position["size"] if position else 0))

    return trades, equity_curve

# ── PRINT RESULTS ─────────────────────────────────────────
def print_results(trades, equity_curve):
    if not trades:
        print("⚠️ No trades were made — conditions too strict!")
        return

    total_trades  = len(trades)
    winners       = [t for t in trades if t["pnl"] > 0]
    losers        = [t for t in trades if t["pnl"] <= 0]
    total_pnl     = sum(t["pnl"] for t in trades)
    win_rate      = len(winners) / total_trades * 100
    avg_win       = sum(t["pnl"] for t in winners) / len(winners) if winners else 0
    avg_loss      = sum(t["pnl"] for t in losers)  / len(losers)  if losers  else 0
    best_trade    = max(trades, key=lambda t: t["pnl"])
    worst_trade   = min(trades, key=lambda t: t["pnl"])
    final_capital = STARTING_CAPITAL + total_pnl
    total_return  = (final_capital - STARTING_CAPITAL) / STARTING_CAPITAL * 100

    peak     = STARTING_CAPITAL
    drawdown = 0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > drawdown:
            drawdown = dd

    print("\n" + "="*55)
    print("  📊 BACKTEST RESULTS")
    print("="*55)
    print(f"  Period        : Last {MONTHS_BACK} months")
    print(f"  Symbol        : {SYMBOL}")
    print(f"  Timeframe     : {TIMEFRAME}")
    print("-"*55)
    print(f"  💰 Starting capital : ${STARTING_CAPITAL:,.2f}")
    print(f"  💰 Final capital    : ${final_capital:,.2f}")
    print(f"  📈 Total return     : {total_return:+.1f}%")
    print(f"  📉 Max drawdown     : -{drawdown:.1f}%")
    print("-"*55)
    print(f"  🔢 Total trades     : {total_trades}")
    print(f"  ✅ Winners          : {len(winners)} ({win_rate:.1f}%)")
    print(f"  ❌ Losers           : {len(losers)} ({100-win_rate:.1f}%)")
    print(f"  💵 Avg win          : ${avg_win:.2f}")
    print(f"  💸 Avg loss         : ${avg_loss:.2f}")
    print(f"  🏆 Best trade       : ${best_trade['pnl']:.2f} ({best_trade['exit_time'].strftime('%Y-%m-%d')})")
    print(f"  💀 Worst trade      : ${worst_trade['pnl']:.2f} ({worst_trade['exit_time'].strftime('%Y-%m-%d')})")
    print("-"*55)

    sl_exits = len([t for t in trades if "Stop" in t["exit_reason"]])
    tp_exits = len([t for t in trades if "Take" in t["exit_reason"]])
    print(f"  🛑 Stop loss exits  : {sl_exits}")
    print(f"  ✅ Take profit exits: {tp_exits}")
    print("="*55)

    if total_return > 20 and win_rate > 55 and drawdown < 15:
        grade = "🟢 EXCELLENT — Consider paper trading this!"
    elif total_return > 5 and win_rate > 45:
        grade = "🟡 DECENT — Needs refinement before live trading"
    elif total_return > 0:
        grade = "🟠 MARGINAL — Barely profitable, needs work"
    else:
        grade = "🔴 POOR — Do not trade this strategy live"

    print(f"\n  Strategy grade: {grade}")
    print("="*55)

    print("\n  📋 Last 5 trades:")
    print(f"  {'Date':<12} {'Dir':<6} {'Entry':>10} {'Exit':>10} {'PnL':>8} {'Reason'}")
    print("  " + "-"*65)
    for t in trades[-5:]:
        print(f"  {t['exit_time'].strftime('%Y-%m-%d'):<12} {t['direction']:<6} ${t['entry_price']:>9,.0f} ${t['exit_price']:>9,.0f} ${t['pnl']:>7.2f} {t['exit_reason']}")

    print("\n✅ Backtest complete!\n")

# ── MAIN ─────────────────────────────────────────────────
if __name__ == "__main__":
    df = fetch_historical_data()
    df = add_indicators(df)
    trades, equity_curve = run_backtest(df)
    print_results(trades, equity_curve)