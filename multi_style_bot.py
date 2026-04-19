"""
DRISSBOT — MULTI-STYLE BOT v2
Day Trade + Swing only (scalping removed)

NEW ARCHITECTURE:
  Agents score → scoring_engine decides → risk_manager executes
  Claude = explanation writer, NOT decision maker

  OLD: technical → Claude decides → Grok vetoes (decision chaos)
  NEW: technical + macro + grok + whale → scoring_engine → ONE decision

Capital: 60% day ($600) / 40% swing ($400)
Cycles:  Day every 1h (Haiku reasoning) | Swing every 4h (Sonnet reasoning)
"""

import datetime, os, time
import requests
from dotenv import load_dotenv
import anthropic

from technical_agent   import TechnicalAgent
from swing_agent       import SwingAgent
from macro_agent       import MacroAgent
from regime_detector   import RegimeDetector
from scoring_engine    import ScoringEngine
from news_scraper      import get_full_sentiment, format_for_ai
from economic_calendar import is_news_blackout, get_macro_context
from grok_agent        import ask_grok
from whale_detector    import analyze_whales, format_whale_summary
from risk_manager      import RiskManager
from performance       import record_trade, update_trade, get_performance_report
from agent_memory      import AgentMemory

load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOG_FILE         = "bot_log.txt"

TOTAL_CAPITAL = 1000.0
COINS         = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

STYLE_CAPITAL = {
    "day"  : TOTAL_CAPITAL * 0.60,
    "swing": TOTAL_CAPITAL * 0.40,
}

CYCLE_TIMES = {"day": 3600, "swing": 14400}
STYLES      = ["day", "swing"]
TICK_SECONDS = 900

# ── INIT ──────────────────────────────────────────────────────────────────────
client      = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
memory      = AgentMemory()
macro_agent = MacroAgent()
regime_det  = RegimeDetector()
scoring_eng = ScoringEngine()
day_trader  = TechnicalAgent()
swinger     = SwingAgent()

risk_managers = {
    style: {coin: RiskManager(total_capital=STYLE_CAPITAL[style] / len(COINS)) for coin in COINS}
    for style in STYLES
}

open_trades  = {style: {coin: None for coin in COINS} for style in STYLES}
last_run     = {style: 0 for style in STYLES}
shared_macro = None

# ── UTILITIES ─────────────────────────────────────────────────────────────────
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
        r   = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
        if not r.json().get("ok"):
            print(f"⚠️ Telegram: {r.text[:80]}")
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

def sync_open_trades_from_db():
    """On startup, reload open trades from DB into memory so the bot
    doesn't lose track of positions after a Railway restart."""
    try:
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, symbol, style
            FROM paper_trades
            WHERE status='OPEN'
            ORDER BY id
        """)
        rows = cur.fetchall()
        conn.close()

        restored = 0
        for trade_id, symbol, style in rows:
            if symbol and style and symbol in COINS and style in STYLES:
                # Only restore if we don't already have one for this slot
                if open_trades[style].get(symbol) is None:
                    open_trades[style][symbol] = trade_id
                    restored += 1
                    log(f"  🔄 Restored: #{trade_id} [{style.upper()}] {symbol}")
            else:
                log(f"  ⚠️ Skipped orphan trade #{trade_id} [{style} {symbol}]")

        log(f"📂 Synced {restored}/{len(rows)} open trades from DB")
    except Exception as e:
        log(f"⚠️ DB sync on startup failed: {e}")

# ── CLAUDE: WRITER ONLY ───────────────────────────────────────────────────────
def ask_claude_explain(symbol: str, style: str, score_result: dict, agent_result: dict) -> str:
    """
    Claude's NEW role: write the Telegram explanation.
    Does NOT output BUY/SELL/HOLD — scoring_engine already decided.
    """
    coin       = symbol.replace("/USDT", "")
    action     = score_result["action"]
    score      = score_result["score"]
    regime     = score_result["regime"]
    breakdown  = score_result["breakdown"]
    style_name = {"day": "DAY TRADE", "swing": "SWING"}[style]
    model      = "claude-haiku-4-5-20251001" if style == "day" else "claude-sonnet-4-6"

    prompt = f"""A trading scoring system decided: {action} {coin} ({style_name})
Score: {score:+.3f} | Regime: {regime}
Signals: Technical={breakdown['technical']:+.2f} Macro={breakdown['macro']:+.2f} Sentiment={breakdown['sentiment']:+.2f} Whale={breakdown['whale']:+.2f}
RSI: {(agent_result.get('raw_data') or {}).get('rsi', '?')} | 4H: {(agent_result.get('raw_data') or {}).get('trend_4h', '?')} | 1D: {(agent_result.get('raw_data') or {}).get('trend_1d', '?')}

Write exactly 2 sentences for a Telegram alert. First: why {action}. Second: main risk. Be specific and concise."""

    try:
        msg = client.messages.create(
            model=model, max_tokens=120,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception:
        return f"Score {score:+.3f} | Regime {regime} | T={breakdown['technical']:+.2f} M={breakdown['macro']:+.2f}"

# ── TRADE EXECUTION ───────────────────────────────────────────────────────────
def check_exits(style, symbol, price):
    trade_id = open_trades[style][symbol]
    if not trade_id:
        return
    hit = update_trade(trade_id, price)
    if hit:
        coin = symbol.replace("/USDT", "")
        log(f"✅ [{style.upper()}] {coin} trade #{trade_id} closed!")

        # Feed outcome back to scoring engine for adaptive weight learning
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
            cur  = conn.cursor()
            cur.execute("""
                SELECT pnl, score,
                       (SELECT action FROM paper_trades WHERE id=%s) as action
                FROM paper_trades WHERE id=%s
            """, (trade_id, trade_id))
            row = cur.fetchone()
            conn.close()
            if row and row[0] is not None:
                actual_pnl = float(row[0])
                # Reconstruct breakdown from stored score (approximate)
                stored_score = float(row[1] or 0)
                approx_breakdown = {
                    "technical" : stored_score * 0.45,
                    "macro"     : stored_score * 0.20,
                    "sentiment" : stored_score * 0.20,
                    "whale"     : stored_score * 0.15,
                }
                scoring_eng.record_closed_trade(approx_breakdown, "RANGING", actual_pnl)
                log(f"  🧠 Feedback recorded: PnL=${actual_pnl:+.2f}")
        except Exception as e:
            log(f"  ⚠️ Feedback error: {e}")

        memory.record_trade_exit(symbol, trade_id, price)
        open_trades[style][symbol] = None
        send_telegram(f"✅ {'📈' if style=='day' else '🌊'} {style.upper()} {coin} Closed!\n\n{get_performance_report()}")

def execute(style, symbol, agent_result, score_result, explanation):
    coin   = symbol.replace("/USDT", "")
    action = score_result["action"]
    conf   = score_result["confidence"]

    price = (agent_result.get("raw_data") or {}).get("price", 0)
    if not price:
        import ccxt
        price = ccxt.binance().fetch_ticker(symbol)["last"]

    check_exits(style, symbol, price)

    rm = risk_managers[style][symbol]
    approved, reason, details = rm.check_trade(action, price, conf, style)

    ae  = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⚪"
    msg = (
        f"{'📈' if style=='day' else '🌊'} [{style.upper()}] {coin}\n"
        f"  ${price:,.2f} | {ae} {action} ({conf.upper()})\n"
        f"  Score: {score_result['score']:+.3f} | Regime: {score_result['regime']}\n"
        f"  {explanation}"
    )

    if approved and not open_trades[style][symbol] and action != "HOLD":
        sl_pct = agent_result.get("sl_pct", 0.03)
        tp_pct = agent_result.get("tp_pct", 0.06)
        sl     = price * (1 - sl_pct) if action == "BUY" else price * (1 + sl_pct)
        tp     = price * (1 + tp_pct) if action == "BUY" else price * (1 - tp_pct)
        size   = details["position_size_usd"]

        trade_id = record_trade(action, price, sl, tp, size, conf,
                               symbol=symbol, style=style,
                               score=score_result.get("score", 0.0))
        open_trades[style][symbol] = trade_id

        memory.record_trade_entry(
            symbol, action, price,
            {"technical": agent_result["signal"], "score": score_result["score"],
             "regime": score_result["regime"], "rsi": (agent_result.get("raw_data") or {}).get("rsi", 0)},
            explanation, conf
        )

        msg += f"\n\n💰 TRADE #{trade_id}\nSL: ${sl:,.2f} | TP: ${tp:,.2f} | Size: ${size:.0f}"
        log(f"✅ [{style.upper()}] {coin} #{trade_id}: {action} @ ${price:,.2f} | score={score_result['score']:+.3f}")

    elif open_trades[style][symbol]:
        log(f"⏳ [{style.upper()}] {coin}: holding #{open_trades[style][symbol]}")
    else:
        msg += f"\n❌ {reason}"
        log(f"❌ [{style.upper()}] {coin}: blocked — {reason}")

    if action in ("BUY", "SELL"):
        send_telegram(msg)

# ── STYLE RUNNERS ─────────────────────────────────────────────────────────────
def run_style(style, agent_fn, news, whale_data=None):
    log(f"\n{'📈' if style=='day' else '🌊'} Running {style.upper()} cycle...")

    for symbol in COINS:
        coin = symbol.replace("/USDT", "")

        if open_trades[style][symbol] is not None:
            try:
                import ccxt
                price = ccxt.binance().fetch_ticker(symbol)["last"]
                check_exits(style, symbol, price)
            except Exception as e:
                log(f"  ⚠️ Exit check {coin}: {e}")
            continue

        if style == "day":
            blackout, reason = is_news_blackout()
            if blackout:
                log(f"  [{style.upper()}] {coin} BLOCKED — {reason}")
                continue

        try:
            # 1. Technical signal
            agent_result = agent_fn(symbol)
            price = (agent_result.get("raw_data") or {}).get("price", 0)

            # 2. Regime gate
            regime = regime_det.classify(symbol)
            if style == "day" and not regime["day_ok"]:
                log(f"  [{style.upper()}] {coin} SKIPPED — {regime['regime']} not suitable for day")
                continue
            if not regime["tradeable"]:
                log(f"  [{style.upper()}] {coin} SKIPPED — CHOP regime, no trades")
                continue

            # 3. Grok sentiment
            grok = None
            try:
                grok = ask_grok(symbol, price, None, agent_result.get("score", 0))
                log(f"  🐦 Grok: {grok['vote']} ({grok['confidence']})")
            except Exception as e:
                log(f"  ⚠️ Grok error: {e}")

            # 4. ONE decision from scoring engine
            score_result = scoring_eng.score(
                technical=agent_result,
                regime=regime,
                style=style,
                macro=shared_macro,
                grok=grok,
                whale=(whale_data or {}).get(symbol),
                news=news,
            )

            log(f"  📊 {coin}: {score_result['action']} (score={score_result['score']:+.3f})")

            if score_result["action"] == "HOLD":
                continue

            # 5. Claude writes explanation (not deciding)
            explanation = ask_claude_explain(symbol, style, score_result, agent_result)

            # 6. Risk manager executes
            execute(style, symbol, agent_result, score_result, explanation)
            time.sleep(3)

        except Exception as e:
            log(f"  ❌ [{style}] {coin} error: {e}")
            continue

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def run_bot():
    global shared_macro

    log("=" * 65)
    log("🤖 DRISSBOT v2 — Scoring Engine Architecture")
    log("  🧠 Decisions: scoring_engine (agents vote → engine decides)")
    log("  📝 Claude: explanation writer only")
    log("  📊 Regime: gates all trades (CHOP = no trades)")
    log(f"  💰 Day ${STYLE_CAPITAL['day']:.0f} | Swing ${STYLE_CAPITAL['swing']:.0f}")
    log("=" * 65)

    send_telegram(
        "🤖 DrissBot v2 Online!\n\n"
        "🧠 Scoring engine architecture:\n"
        "   All agents vote → engine decides → Claude explains\n\n"
        "📊 Regime detection active — CHOP markets = no trades\n"
        "📈 Day 1h | 🌊 Swing 4h\n"
        f"💰 Day ${STYLE_CAPITAL['day']:.0f} | Swing ${STYLE_CAPITAL['swing']:.0f}"
    )

    cycle = 0
    sync_open_trades_from_db()

    while True:
        try:
            now = time.time()
            cycle += 1
            log(f"\n{'='*65}")
            log(f"⏰ Tick #{cycle} — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            # Macro refresh every hour
            if cycle == 1 or cycle % 4 == 0:
                try:
                    shared_macro = macro_agent.analyze()
                    log(f"  📊 Macro: {shared_macro.get('regime','?')} | "
                        f"F&G: {(shared_macro.get('fear_greed') or {}).get('value','?')}")
                except Exception as e:
                    log(f"  ⚠️ Macro: {e}")
                    shared_macro = None

            try:
                news = format_for_ai(get_full_sentiment())
            except Exception as e:
                log(f"⚠️ News: {e}")
                news = "No news available"

            try:
                whale_data = {coin: analyze_whales(coin) for coin in COINS}
            except Exception as e:
                log(f"⚠️ Whale: {e}")
                whale_data = {}

            if now - last_run["day"] >= CYCLE_TIMES["day"]:
                run_style("day", day_trader.analyze, news, whale_data)
                last_run["day"] = now

            if now - last_run["swing"] >= CYCLE_TIMES["swing"]:
                run_style("swing", swinger.analyze, news, whale_data)
                last_run["swing"] = now

            # Daily report
            if cycle % int(86400 / TICK_SECONDS) == 0 and cycle > 0:
                stats   = memory.get_stats()
                acc_str = scoring_eng.format_stats_for_telegram()
                send_telegram(
                    f"📊 Daily Report\n\n{get_performance_report()}\n\n"
                    f"{acc_str}\n\n"
                    f"Win rate: {stats.get('win_rate',0)}% | P&L: ${stats.get('total_pnl',0):+,.2f}"
                )

            log(f"💤 Next tick in {TICK_SECONDS//60}min...")
            time.sleep(TICK_SECONDS)

        except KeyboardInterrupt:
            log("🛑 Bot stopped")
            send_telegram("🛑 DrissBot stopped")
            break
        except Exception as e:
            log(f"❌ Main error: {e}")
            send_telegram(f"❌ Error: {e}. Retrying in 60s...")
            time.sleep(60)


if __name__ == "__main__":
    run_bot()
