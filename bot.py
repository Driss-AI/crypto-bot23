import anthropic
import ccxt
import datetime
import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv
from risk_manager import RiskManager
from news_fetcher import get_latest_news
import os
import time
import requests

# ── SETUP ────────────────────────────────────────────────
load_dotenv()
api_key          = os.getenv("ANTHROPIC_API_KEY") or "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"
TELEGRAM_TOKEN   = "8707992591:AAEqkOc0pmK1rAEYVnMnh8DdK7KmaLGLiSA"
TELEGRAM_CHAT_ID = "6463217777"

client   = anthropic.Anthropic(api_key=api_key)
exchange = ccxt.binance()
rm       = RiskManager(total_capital=1000)
LOG_FILE = "bot_log.txt"

# ── TELEGRAM ─────────────────────────────────────────────
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={
            "chat_id"    : TELEGRAM_CHAT_ID,
            "text"       : message,
            "parse_mode" : "HTML"
        })
        print(f"📱 Telegram: {r.json().get('ok')}")
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

# ── LOGGING ──────────────────────────────────────────────
def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ── STEP 1: FETCH MARKET DATA ────────────────────────────
def get_market_data():
    log("📡 Fetching market data from Binance...")
    candles = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)
    df = pd.DataFrame(candles, columns=["timestamp","open","high","low","close","volume"])

    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"])
    df["macd"]        = macd.iloc[:, 0]
    df["macd_signal"] = macd.iloc[:, 1]
    bb = ta.bbands(df["close"], length=20)
    df["bb_upper"] = bb.iloc[:, 0]
    df["bb_lower"] = bb.iloc[:, 1]
    df["bb_mid"]   = bb.iloc[:, 2]
    df["volume_avg"] = df["volume"].rolling(20).mean()

    latest = df.iloc[-1]
    return {
        "price"    : latest["close"],
        "rsi"      : latest["rsi"],
        "macd"     : latest["macd"],
        "macd_sig" : latest["macd_signal"],
        "bb_upper" : latest["bb_upper"],
        "bb_lower" : latest["bb_lower"],
        "bb_mid"   : latest["bb_mid"],
        "volume"   : latest["volume"],
        "vol_avg"  : latest["volume_avg"],
    }

# ── STEP 2: ASK CLAUDE ───────────────────────────────────
def ask_claude(data):
    log("🧠 Asking Claude AI for analysis...")

    # Get latest news + Fear & Greed
    news = get_latest_news()

    prompt = f"""
You are an expert crypto trading analyst. Analyze this Bitcoin market data and respond in this EXACT format:

ACTION: [BUY or SELL or HOLD]
CONFIDENCE: [high or medium or low]
REASONING: [2-3 sentences max]
RISKS: [1-2 key risks]

Market data as of {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}:
- Price: ${data['price']:,.2f}
- RSI: {data['rsi']:.1f} ({'Oversold' if data['rsi'] < 30 else 'Overbought' if data['rsi'] > 70 else 'Neutral'})
- MACD: {data['macd']:.2f} vs Signal {data['macd_sig']:.2f} ({'Bullish' if data['macd'] > data['macd_sig'] else 'Bearish'})
- Bollinger: Upper ${data['bb_upper']:,.0f} | Mid ${data['bb_mid']:,.0f} | Lower ${data['bb_lower']:,.0f}
- Price vs bands: {'Above upper - stretched' if data['price'] > data['bb_upper'] else 'Below lower - stretched' if data['price'] < data['bb_lower'] else 'Inside bands - normal'}
- Volume: {data['volume']:,.0f} vs avg {data['vol_avg']:,.0f} ({'High' if data['volume'] > data['vol_avg'] else 'Low'})

{news}

Consider ALL data including news sentiment and Fear & Greed index carefully.
Be decisive. Give a clear action.
"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    response   = message.content[0].text
    action     = "HOLD"
    confidence = "medium"
    reasoning  = ""
    risks      = ""

    for line in response.split("\n"):
        if line.startswith("ACTION:"):
            action = line.replace("ACTION:", "").strip().upper()
        if line.startswith("CONFIDENCE:"):
            confidence = line.replace("CONFIDENCE:", "").strip().lower()
        if line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()
        if line.startswith("RISKS:"):
            risks = line.replace("RISKS:", "").strip()

    log(f"🤖 Claude: {action} ({confidence})")
    return action, confidence, reasoning, risks

# ── STEP 3: PAPER TRADE + TELEGRAM ───────────────────────
def paper_trade(action, confidence, reasoning, risks, data):
    price = data["price"]
    approved, reason, details = rm.check_trade(action, price, confidence)

    action_emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "🟡"
    conf_emoji   = "💪" if confidence == "high" else "👍" if confidence == "medium" else "🤔"

    msg = f"""🤖 <b>BTC Analysis</b>
🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}

💰 <b>Price:</b> ${price:,.2f}
📊 RSI: {data['rsi']:.1f} | MACD: {'Bullish 📈' if data['macd'] > data['macd_sig'] else 'Bearish 📉'}

{action_emoji} <b>Decision: {action}</b>
{conf_emoji} Confidence: {confidence.upper()}

🧠 {reasoning}
⚠️ {risks}"""

    if approved:
        msg += f"""

✅ <b>PAPER TRADE:</b>
- Size: ${details['position_size_usd']}
- Stop loss: ${details['stop_loss']:,}
- Take profit: ${details['take_profit']:,}"""
        log(f"📝 Paper trade: {action} @ ${price:,}")
    else:
        msg += f"\n\n⏸️ No trade — {reason}"
        log(f"⏸️ No trade: {reason}")

    send_telegram(msg)

# ── MAIN LOOP ─────────────────────────────────────────────
def run_bot():
    log("="*50)
    log("🚀 CRYPTO BOT STARTING — PAPER TRADING MODE")
    log("="*50)

    send_telegram("🚀 <b>Crypto Bot Started!</b>\n\n📊 Watching BTC/USDT 24/7\n⏰ Analysis every hour\n🛡️ Risk management active\n📰 News sentiment enabled!")

    while True:
        try:
            log("\n" + "-"*50)
            log("🔄 New analysis cycle starting...")

            data = get_market_data()
            log(f"💰 BTC: ${data['price']:,.2f} | RSI: {data['rsi']:.1f}")

            action, confidence, reasoning, risks = ask_claude(data)

            paper_trade(action, confidence, reasoning, risks, data)

            log("⏰ Next analysis in 1 hour...")
            time.sleep(3600)

        except Exception as e:
            log(f"⚠️ Error: {e}")
            send_telegram(f"⚠️ <b>Bot Error</b>\n{e}")
            time.sleep(60)

if __name__ == "__main__":
    run_bot()