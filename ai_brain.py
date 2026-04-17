import anthropic
import ccxt
import datetime
import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv
import os

# Load your secret API key from .env file
load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")

#  FETCH MARKET DATA 
exchange = ccxt.binance()
print(" Fetching Bitcoin market data...")
candles = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)
df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

#  CALCULATE INDICATORS 
df["rsi"] = ta.rsi(df["close"], length=14)
macd = ta.macd(df["close"])
df["macd"] = macd.iloc[:, 0]
df["macd_signal"] = macd.iloc[:, 1]
bb = ta.bbands(df["close"], length=20)
df["bb_upper"] = bb.iloc[:, 0]
df["bb_lower"] = bb.iloc[:, 1]
df["bb_mid"]   = bb.iloc[:, 2]
df["volume_avg"] = df["volume"].rolling(20).mean()

#  GET LATEST VALUES 
latest = df.iloc[-1]
price    = latest["close"]
rsi      = latest["rsi"]
macd_val = latest["macd"]
macd_sig = latest["macd_signal"]
bb_upper = latest["bb_upper"]
bb_lower = latest["bb_lower"]
bb_mid   = latest["bb_mid"]
volume   = latest["volume"]
vol_avg  = latest["volume_avg"]

#  BUILD MARKET SUMMARY FOR CLAUDE 
market_summary = f"""
Here is the current Bitcoin (BTC/USDT) market data as of {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}:

- Price: ${price:,.2f}
- RSI (14): {rsi:.1f} ({'Oversold' if rsi < 30 else 'Overbought' if rsi > 70 else 'Neutral'})
- MACD: {macd_val:.2f} vs Signal {macd_sig:.2f} ({'Bullish' if macd_val > macd_sig else 'Bearish'})
- Bollinger Bands: Upper ${bb_upper:,.0f} | Mid ${bb_mid:,.0f} | Lower ${bb_lower:,.0f}
- Price vs Bands: {'Above upper band - stretched' if price > bb_upper else 'Below lower band - stretched' if price < bb_lower else 'Inside bands - normal'}
- Volume: {volume:,.0f} vs 20-period avg {vol_avg:,.0f} ({'High' if volume > vol_avg else 'Low'})

Based on this data, please analyze the market and give me:
1. Your overall market assessment
2. Whether you would BUY, SELL, or HOLD right now
3. Your reasoning in simple terms
4. Key risks to watch out for

Be concise but thorough. Think like an experienced crypto trader.
"""

#  ASK CLAUDE AI 
print(" Asking Claude AI for analysis...\n")
client = anthropic.Anthropic(api_key=api_key)

message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": market_summary
        }
    ]
)

#  PRINT CLAUDE'S RESPONSE 
print("="*55)
print("   CLAUDE AI TRADING ANALYSIS")
print("="*55)
print(message.content[0].text)
print("="*55)
print("\n Analysis complete!\n")