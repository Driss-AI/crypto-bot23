"""
MULTI-COIN BOT v2  fetches macro ONCE per cycle, shares with all orchestrators
Fixes: CoinGecko rate limits, SOL/BNB NoneType errors
"""

import datetime, os, time
import requests
from dotenv import load_dotenv

from orchestrator import Orchestrator
from macro_agent     import MacroAgent
from performance     import record_trade, update_trade, get_performance_report
from agent_memory    import AgentMemory

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOG_FILE         = "bot_log.txt"
TOTAL_CAPITAL    = 1000.0
COINS            = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

ORCHESTRATORS = {
    coin: Orchestrator(total_capital=TOTAL_CAPITAL / len(COINS))
    for coin in COINS
}

open_trades: dict = {coin: None for coin in COINS}
memory = AgentMemory()
macro_agent = MacroAgent()


def log(msg):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r   = requests.post(url, data={"chat_id":TELEGRAM_CHAT_ID,"text":msg,"parse_mode":"HTML"}, timeout=10)
        if not r.json().get("ok"):
            print(f" Telegram: {r.text[:80]}")
    except Exception as e:
        print(f" Telegram error: {e}")


def check_exits(symbol, price):
    trade_id = open_trades[symbol]
    if not trade_id:
        return
    hit = update_trade(trade_id, price)
    if hit:
        coin = symbol.replace("/USDT","")
        log(f" {coin} trade #{trade_id} closed!")
        open_trades[symbol] = None
        send_telegram(f" <b>{coin} Trade Closed!</b>\n\n{get_performance_report()}")
        memory.print_stats()


def execute_decision(symbol, result):
    coin   = symbol.replace("/USDT","")
    action = result["action"]
    conf   = result["confidence"]
    price  = result["price"]

    check_exits(symbol, price)

    ae = "" if action=="BUY" else "" if action=="SELL" else ""
    ce = "" if conf=="high" else "" if conf=="medium" else ""

    agents = result.get("agents", {})
    tech   = agents.get("technical") or {}
    macro  = agents.get("macro")     or {}

    fg_line = ""
    if macro.get("fear_greed"):
        fg_line = f"\n Fear & Greed: {macro['fear_greed']['value']}/100"

    msg = (
        f" <b>{coin}  Multi-Agent Analysis</b>\n"
        f" {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f" <b>Price:</b> ${price:,.2f}\n"
        f" RSI 1h: {(tech.get('raw_data') or {}).get('rsi',0):.1f}"
        f" | 4H: {(tech.get('raw_data') or {}).get('trend_4h','?')}\n"
        f" Macro: {macro.get('regime','?')}{fg_line}\n"
        f" Consensus: {result['consensus_score']:+.3f}\n\n"
        f"{ae} <b>DECISION: {action}</b>\n"
        f"{ce} Confidence: {conf.upper()}\n\n"
        f" {result['reasoning']}\n"
        f" {result['risks']}"
    )

    if result["approved"] and not open_trades[symbol] and action != "HOLD":
        td = result["trade_details"]
        trade_id = record_trade(action, price, td["stop_loss"],
                                td["take_profit"], td["position_size_usd"], conf)
        open_trades[symbol] = trade_id
        memory.record_trade_entry(symbol, action, price,
                                  result["signals"], result["reasoning"], conf)
        msg += (
            f"\n\n <b>PAPER TRADE #{trade_id}</b>\n"
            f"- Size: ${td['position_size_usd']}\n"
            f"- Entry: ${price:,.2f}\n"
            f"- Stop: ${td['stop_loss']:,.2f} | TP: ${td['take_profit']:,.2f}"
        )
        log(f" {coin} #{trade_id}: {action} @ ${price:,.2f}")
    elif open_trades[symbol]:
        msg += f"\n\n Trade #{open_trades[symbol]} still open"
        log(f" {coin}: holding #{open_trades[symbol]}")
    else:
        msg += f"\n\n {result['risk_reason']}"
        log(f" {coin}: {action} ({conf})  {result['risk_reason']}")

    send_telegram(msg)


def run_bot():
    log("="*55)
    log(" MULTI-AGENT BOT v2 STARTING")
    log(f" Coins: {', '.join(COINS)}")
    log(f" Capital: ${TOTAL_CAPITAL} (${TOTAL_CAPITAL/len(COINS):.0f}/coin)")
    log("="*55)

    coins_str = ", ".join(c.replace("/USDT","") for c in COINS)
    send_telegram(
        f" <b>Multi-Agent Bot v2 Started!</b>\n\n"
        f" Coins: {coins_str}\n"
        f" Agents: Technical + Macro + On-Chain + Sentiment\n"
        f" Macro fetched ONCE per cycle (no rate limits)\n"
        f" Capital: ${TOTAL_CAPITAL} total"
    )

    cycle = 0
    while True:
        try:
            cycle += 1
            log(f"\n{'='*55}")
            log(f" Cycle #{cycle}  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
            log(f"{'='*55}")

            #  Fetch macro ONCE for all coins 
            log(" Fetching macro data (shared across all coins)...")
            try:
                shared_macro = macro_agent.analyze()
                log(f" Macro: {shared_macro.get('regime','?')} | Score: {shared_macro.get('score',0):+d}")
            except Exception as e:
                log(f" Macro failed: {e}")
                shared_macro = None

            # Set shared macro on all orchestrators
            for orch in ORCHESTRATORS.values():
                orch.shared_macro = shared_macro

            #  Analyze each coin 
            for symbol in COINS:
                coin = symbol.replace("/USDT","")
                try:
                    log(f"\n Analyzing {coin}...")
                    result = ORCHESTRATORS[symbol].analyze(symbol)
                    ORCHESTRATORS[symbol].print_decision(result)
                    execute_decision(symbol, result)
                    time.sleep(10)   # pause between coins
                except Exception as e:
                    log(f" {coin} error: {e}")
                    send_telegram(f" <b>{coin} Error</b>\n{e}")
                    continue

            #  Daily report 
            if cycle % 24 == 0:
                stats = memory.get_stats()
                send_telegram(
                    f" <b>Daily Report  Cycle {cycle}</b>\n\n"
                    f"{get_performance_report()}\n\n"
                    f" Patterns learned: {stats['patterns_discovered']}\n"
                    f"Win rate: {stats['win_rate']}% | P&L: ${stats['total_pnl']:+,.2f}"
                )
                log(" Daily report sent")

            log(f"\n Next cycle in 1 hour...")
            time.sleep(3600)

        except KeyboardInterrupt:
            log(" Bot stopped by user")
            send_telegram(" <b>Bot stopped</b>")
            break
        except Exception as e:
            log(f" Main error: {e}")
            send_telegram(f" <b>Error</b>\n{e}\nRetrying in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    run_bot()
