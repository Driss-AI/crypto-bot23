"""
MULTI-STYLE BOT
Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
Runs 3 trading styles ÃÂ 4 coins = 12 independent strategies

Ã°ÂÂÂ¥ Scalper    Ã¢ÂÂ every 5 min  | SL 0.5% | TP 1%  | 5% size
Ã°ÂÂÂ Day Trader Ã¢ÂÂ every 1 hour | SL 3%   | TP 6%  | 2% size
Ã°ÂÂÂ Swing      Ã¢ÂÂ every 4 hours| SL 8%   | TP 16% | 1% size

Each style runs independently and manages its own trades.
All decisions go through Claude + RiskManager.
Everything recorded in AgentMemory for learning.
"""

import datetime, os, time, threading
import requests
from dotenv import load_dotenv
import anthropic

from scalper_agent   import ScalperAgent
from technical_agent import TechnicalAgent   # day trade agent
from swing_agent     import SwingAgent
from macro_agent     import MacroAgent
from news_scraper    import get_full_sentiment, format_for_ai
from economic_calendar import is_news_blackout, get_macro_context
from whale_detector  import analyze_whales, format_whale_summary
from risk_manager    import RiskManager
from performance     import record_trade, update_trade, get_performance_report
from agent_memory    import AgentMemory

load_dotenv()

# Ã¢ÂÂÃ¢ÂÂ CONFIG Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOG_FILE         = "bot_log.txt"
TOTAL_CAPITAL    = 1000.0

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

# Capital split: 40% scalp / 40% day / 20% swing
STYLE_CAPITAL = {
    "scalp": TOTAL_CAPITAL * 0.40,
    "day"  : TOTAL_CAPITAL * 0.40,
    "swing": TOTAL_CAPITAL * 0.20,
}

# Cycle times in seconds
CYCLE_TIMES = {
    "scalp": 60,     # ✅ 1 min — scalping needs fast reaction
    "day"  : 3600,   # 1 hour
    "swing": 14400,  # 4 hours
}

# Ã¢ÂÂÃ¢ÂÂ INIT Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
client      = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
memory      = AgentMemory()
macro_agent = MacroAgent()

# One agent instance per style
scalper    = ScalperAgent()
day_trader = TechnicalAgent()
swinger    = SwingAgent()

# Risk managers per style (capital split equally across coins)
risk_managers = {
    style: {
        coin: RiskManager(total_capital=STYLE_CAPITAL[style] / len(COINS))
        for coin in COINS
    }
    for style in ["scalp", "day", "swing"]
}

# Track open trades: style Ã¢ÂÂ coin Ã¢ÂÂ trade_id
open_trades = {
    style: {coin: None for coin in COINS}
    for style in ["scalp", "day", "swing"]
}

# Track last run time per style
last_run = {style: 0 for style in ["scalp", "day", "swing"]}
open_positions = set()   # prevents stacking duplicate trades

# Shared macro (fetched once per day cycle)
shared_macro = None


def sync_open_trades_from_db():
    """On startup, reload open trades from paper_trades into open_trades dict."""
    try:
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, action FROM paper_trades WHERE status='OPEN'
        """)
        rows = cur.fetchall()
        conn.close()
        log(f"Ã°ÂÂÂ Found {len(rows)} open trades in DB on startup")
    except Exception as e:
        log(f"Ã¢ÂÂ Ã¯Â¸Â DB sync on startup failed: {e}")


# Ã¢ÂÂÃ¢ÂÂ UTILITIES Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

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
        r   = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID, "text": msg, 
        }, timeout=10)
        if not r.json().get("ok"):
            print(f"Ã¢ÂÂ Ã¯Â¸Â Telegram: {r.text[:80]}")
    except Exception as e:
        print(f"Ã¢ÂÂ Ã¯Â¸Â Telegram error: {e}")


# Ã¢ÂÂÃ¢ÂÂ CLAUDE DECISION Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def ask_claude(symbol, style, agent_result, macro, news, whale_data=None) -> dict:
    coin   = symbol.replace("/USDT", "")
    data   = agent_result.get("raw_data", {})
    signal = agent_result.get("signal", "HOLD")
    score  = agent_result.get("score", 0)

    style_emoji = {"scalp": "Ã°ÂÂÂ¥", "day": "Ã°ÂÂÂ", "swing": "Ã°ÂÂÂ"}[style]
    style_name  = {"scalp": "SCALP", "day": "DAY TRADE", "swing": "SWING"}[style]

    macro_text = "Macro unavailable"
    cal_context = get_macro_context()
    if macro:
        fg         = macro.get("fear_greed") or {}
        macro_text = (
            f"Regime: {macro.get('regime','?')} | Score: {macro.get('score',0):+d}\n"
            f"Fear & Greed: {fg.get('value','?')}/100 ({fg.get('label','?')})"
        )

    whale = (whale_data or {}).get(symbol, {})
    whale_text = format_whale_summary(whale) if whale else 'No whale data'

    prompt = f"""You are a crypto trading AI specializing in {style_name} trading.

{style_emoji} STYLE: {style_name}
- Stop Loss: {agent_result['sl_pct']*100:.1f}%
- Take Profit: {agent_result['tp_pct']*100:.1f}%
- Position Size: {agent_result['size_pct']*100:.0f}% of allocated capital

Ã°ÂÂÂ {style_name} AGENT SIGNAL: {signal} (score: {score:+d})
Why: {agent_result.get('reasoning', '')}

Ã°ÂÂÂ° Market: {coin}/USDT @ ${data.get('price', 0):,.2f}

Ã°ÂÂÂ MACRO:
{macro_text}

Ã°ÂÂÂ° SENTIMENT (summary):
{news[:400]}

ECONOMIC CALENDAR:
{cal_context}

{whale_text}

Make the FINAL {style_name} decision. Respond EXACTLY:
ACTION: [BUY or SELL or HOLD]
CONFIDENCE: [high or medium or low]
REASONING: [1-2 sentences specific to {style_name} style]
RISKS: [1 key risk]

{style_name} rules:
{"- Only scalp when volume is HIGH Ã¢ÂÂ never trade thin markets" if style == "scalp" else ""}
{"- Confirm with both 1h and 4h before entering" if style == "day" else ""}
{"- Only swing trade with 1D trend Ã¢ÂÂ never fight the daily" if style == "swing" else ""}
- HOLD is always valid Ã¢ÂÂ missing a trade is better than a bad trade
"""

    msg = client.messages.create(
        model=("claude-haiku-4-5-20251001" if style == "scalp" else "claude-sonnet-4-6"), max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text
    a, c, r, ri = "HOLD", "medium", "", ""
    for line in text.strip().splitlines():
        if line.startswith("ACTION:"):      a  = line.split(":",1)[1].strip().upper()
        elif line.startswith("CONFIDENCE:"): c  = line.split(":",1)[1].strip().lower()
        elif line.startswith("REASONING:"): r  = line.split(":",1)[1].strip()
        elif line.startswith("RISKS:"):     ri = line.split(":",1)[1].strip()
    return {"action": a, "confidence": c, "reasoning": r, "risks": ri}


# Ã¢ÂÂÃ¢ÂÂ TRADE EXECUTION Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def check_exits(style, symbol, price):
    trade_id = open_trades[style][symbol]
    if not trade_id:
        return
    hit = update_trade(trade_id, price)
    if hit:
        coin  = symbol.replace("/USDT", "")
        emoji = {"scalp": "Ã°ÂÂÂ¥", "day": "Ã°ÂÂÂ", "swing": "Ã°ÂÂÂ"}[style]
        log(f"Ã°ÂÂÂ [{style.upper()}] {coin} trade #{trade_id} closed!")
        memory.record_trade_exit(symbol, trade_id, price)
        open_trades[style][symbol] = None
        send_telegram(
            f"Ã°ÂÂÂ <b>{emoji} {style.upper()} {coin} Trade Closed!</b>\n\n"
            f"{get_performance_report()}"
        )


def execute(style, symbol, agent_result, final, macro):
    coin   = symbol.replace("/USDT", "")
    action = final["action"]
    conf   = final["confidence"]
    price  = (agent_result.get("raw_data") or {}).get("price", 0)

    if price == 0:
        log(f"  Ã¢ÂÂ Ã¯Â¸Â [{style}] {coin}: price is 0, skipping")
        return

    check_exits(style, symbol, price)

    rm       = risk_managers[style][coin + "/USDT" if "/" not in coin else coin]
    rm       = risk_managers[style][symbol]
    approved, reason, details = rm.check_trade(action, price, conf, style)

    style_emoji = {"scalp": "Ã°ÂÂÂ¥", "day": "Ã°ÂÂÂ", "swing": "Ã°ÂÂÂ"}[style]
    ae = "Ã°ÂÂÂ¢" if action == "BUY" else "Ã°ÂÂÂ´" if action == "SELL" else "Ã°ÂÂÂ¡"

    msg = (
        f"{style_emoji} <b>[{style.upper()}] {coin}</b>\n"
        f"Ã°ÂÂÂ° ${price:,.2f} | {ae} <b>{action}</b> ({conf.upper()})\n"
        f"Ã°ÂÂ§Â  {final['reasoning']}\n"
        f"Ã¢ÂÂ Ã¯Â¸Â {final['risks']}"
    )

    if approved and not open_trades[style][symbol] and action != "HOLD":
        # Override SL/TP with style-specific values
        sl_pct = agent_result.get("sl_pct", 0.03)
        sl  = price * (1 - sl_pct) if action == "BUY" else price * (1 + agent_result["sl_pct"])
        tp_pct = agent_result.get("tp_pct", 0.06)
        tp  = price * (1 + tp_pct) if action == "BUY" else price * (1 - agent_result["tp_pct"])
        size_pct = agent_result.get("size_pct", 0.02)
        size = details["position_size_usd"]  # Ã¢ÂÂ use risk manager approved size

        trade_id = record_trade(action, price, sl, tp, size, conf)
        open_trades[style][symbol] = trade_id

        signals = {
            "technical": agent_result["signal"],
            "sentiment": "NEUTRAL",
            "macro"    : macro["signal"] if macro else "UNKNOWN",
            "onchain"  : "UNKNOWN",
            "rsi"      : (agent_result.get("raw_data") or {}).get("rsi", 0),
            "fear_greed": ((macro or {}).get("fear_greed") or {}).get("value", 50),
        }
        memory.record_trade_entry(symbol, action, price, signals, final["reasoning"], conf)

        msg += (
            f"\n\nÃ¢ÂÂ <b>TRADE #{trade_id}</b>\n"
            f"SL: ${sl:,.2f} | TP: ${tp:,.2f} | Size: ${size:.0f}"
        )
        log(f"Ã°ÂÂÂ [{style.upper()}] {coin} #{trade_id}: {action} @ ${price:,.2f}")

    elif open_trades[style][symbol]:
        msg += f"\nÃ¢ÂÂ³ Trade #{open_trades[style][symbol]} open"
        log(f"Ã¢ÂÂ³ [{style.upper()}] {coin}: holding #{open_trades[style][symbol]}")
    else:
        msg += f"\nÃ¢ÂÂ¸Ã¯Â¸Â {reason}"
        log(f"Ã¢ÂÂ¸Ã¯Â¸Â [{style.upper()}] {coin}: {action} Ã¢ÂÂ {reason}")

    send_telegram(msg)


# Ã¢ÂÂÃ¢ÂÂ STYLE RUNNERS Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def run_style(style, agent_fn, news, whale_data=None):
    """Run one style across all coins."""
    global shared_macro
    style_emoji = {"scalp": "Ã°ÂÂÂ¥", "day": "Ã°ÂÂÂ", "swing": "Ã°ÂÂÂ"}[style]
    log(f"\n{style_emoji} Running {style.upper()} cycle...")

    for symbol in COINS:
        coin = symbol.replace("/USDT", "")
        if open_trades[style][symbol] is not None:
            log(f"Ã¢ÂÂ­Ã¯Â¸Â  [{style.upper()}] {coin} Ã¢ÂÂ trade open, skipping")
            continue
        if style in ("scalp", "day"):
            blackout, reason = is_news_blackout()
            if blackout:
                log(f"[{style.upper()}] {coin} BLOCKED - {reason}")
                continue
        try:
            result = agent_fn(symbol)
            final  = ask_claude(symbol, style, result, shared_macro, news, whale_data)
            execute(style, symbol, result, final, shared_macro)
            time.sleep(3)
        except Exception as e:
            log(f"Ã¢ÂÂ Ã¯Â¸Â [{style}] {coin} error: {e}")
            continue


# Ã¢ÂÂÃ¢ÂÂ MAIN LOOP Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def run_bot():
    global shared_macro

    log("="*55)
    log("Ã°ÂÂÂ MULTI-STYLE BOT STARTING")
    log(f"Ã°ÂÂÂ¥ Scalp: every 5min | Ã°ÂÂÂ Day: every 1h | Ã°ÂÂÂ Swing: every 4h")
    log(f"Ã°ÂÂÂ Coins: {', '.join(COINS)}")
    log(f"Ã°ÂÂÂ° Capital: Scalp ${STYLE_CAPITAL['scalp']:.0f} | "
        f"Day ${STYLE_CAPITAL['day']:.0f} | Swing ${STYLE_CAPITAL['swing']:.0f}")
    log("="*55)

    send_telegram(
        "Ã°ÂÂÂ <b>Multi-Style Bot Started!</b>\n\n"
        "Ã°ÂÂÂ¥ <b>Scalp</b>: every 5min | SL 0.5% | TP 1%\n"
        "Ã°ÂÂÂ <b>Day Trade</b>: every 1h | SL 3% | TP 6%\n"
        "Ã°ÂÂÂ <b>Swing</b>: every 4h | SL 8% | TP 16%\n\n"
        f"Ã°ÂÂÂ Coins: BTC / ETH / SOL / BNB\n"
        f"Ã°ÂÂÂ° Total: ${TOTAL_CAPITAL:.0f}"
    )

    cycle = 0
    sync_open_trades_from_db()

    while True:
        try:
            now   = time.time()
            cycle += 1

            # Ã¢ÂÂÃ¢ÂÂ Fetch shared data once Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            log(f"\n{'='*55}")
            log(f"Ã°ÂÂÂ Tick #{cycle} Ã¢ÂÂ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # Refresh macro every hour
            if cycle == 1 or cycle % 12 == 0:
                try:
                    log("Ã°ÂÂÂ Refreshing macro data...")
                    shared_macro = macro_agent.analyze()
                    log(f"Ã¢ÂÂ Macro: {shared_macro.get('regime','?')}")
                except Exception as e:
                    log(f"Ã¢ÂÂ Ã¯Â¸Â Macro failed: {e}")
                    shared_macro = None

            # Fetch news + whales once per tick
            try:
                sentiment = get_full_sentiment()
                news = format_for_ai(sentiment)
            except Exception as e:
                log(f'Ã¢ÂÂ Ã¯Â¸Â News error: {e}')
                news = 'No news available'
            try:
                whale_data = {coin: analyze_whales(coin) for coin in COINS}
            except Exception as e:
                log(f'Ã¢ÂÂ Ã¯Â¸Â Whale error: {e}')
                whale_data = {}

            # Ã¢ÂÂÃ¢ÂÂ Scalp: every 5 min Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            if now - last_run["scalp"] >= CYCLE_TIMES["scalp"]:
                run_style("scalp", scalper.analyze, news, whale_data)
                last_run["scalp"] = now

            # Ã¢ÂÂÃ¢ÂÂ Day trade: every 1 hour Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            if now - last_run["day"] >= CYCLE_TIMES["day"]:
                run_style("day", day_trader.analyze, news, whale_data)
                last_run["day"] = now

            # Ã¢ÂÂÃ¢ÂÂ Swing: every 4 hours Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
            if now - last_run["swing"] >= CYCLE_TIMES["swing"]:
                run_style("swing", swinger.analyze, news, whale_data)
                last_run["swing"] = now

            # Ã¢ÂÂÃ¢ÂÂ Daily performance report Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ
                        if cycle % (24 * 12 * 7) == 0 and cycle > 0:   # every 7 days
                try:
                    log("Running weekly review...")
                    import subprocess
                    subprocess.run(["python3", "weekly_review.py"], check=True)
                except Exception as e:
                    log(f"Weekly review failed: {e}")

            if cycle % (24 * 12) == 0:   # every 24h (12 ticks/hour ÃÂ 24)
                stats = memory.get_stats()
                send_telegram(
                    f"Ã°ÂÂÂ <b>Daily Report</b>\n\n"
                    f"{get_performance_report()}\n\n"
                    f"Ã°ÂÂ§Â  Patterns: {stats['patterns_discovered']}\n"
                    f"Win rate: {stats['win_rate']}% | P&L: ${stats['total_pnl']:+,.2f}"
                )

            log("Ã¢ÂÂ° Next tick in 5 minutes (scalp cycle)...")
            time.sleep(300)   # tick every 5 min (scalp frequency)

        except KeyboardInterrupt:
            log("Ã°ÂÂÂ Bot stopped by user")
            send_telegram("Ã°ÂÂÂ <b>Multi-Style Bot stopped</b>")
            break
        except Exception as e:
            log(f"Ã¢ÂÂ Ã¯Â¸Â Main error: {e}")
            send_telegram(f"Ã¢ÂÂ Ã¯Â¸Â <b>Error</b>\n{e}\nRetrying in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    run_bot()
