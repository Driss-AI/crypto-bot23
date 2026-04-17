import ccxt
import datetime
import pandas as pd
import pandas_ta as ta
import urllib.request
import json

#  CONNECT TO BINANCE 
exchange = ccxt.binance()

print(" Fetching Bitcoin market data...")
candles = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)

df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

#  INDICATORS 
df["rsi"] = ta.rsi(df["close"], length=14)

macd = ta.macd(df["close"])
df["macd"] = macd.iloc[:, 0]
df["macd_signal"] = macd.iloc[:, 1]

bb = ta.bbands(df["close"], length=20)
df["bb_upper"] = bb.iloc[:, 0]
df["bb_lower"] = bb.iloc[:, 1]
df["bb_mid"]   = bb.iloc[:, 2]

df["volume_avg"] = df["volume"].rolling(20).mean()

#  LATEST VALUES 
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

#  FEAR & GREED INDEX (free API) 
print(" Fetching Fear & Greed Index...")
try:
    url = "https://api.alternative.me/fng/?limit=1"
    with urllib.request.urlopen(url) as response:
        fng_data = json.loads(response.read())
    fng_value = int(fng_data["data"][0]["value"])
    fng_label = fng_data["data"][0]["value_classification"]

    if fng_value <= 25:
        fng_signal = " EXTREME FEAR  possible buy opportunity"
    elif fng_value <= 45:
        fng_signal = " FEAR  market is worried"
    elif fng_value <= 55:
        fng_signal = " NEUTRAL  no strong sentiment"
    elif fng_value <= 75:
        fng_signal = " GREED  people are excited"
    else:
        fng_signal = " EXTREME GREED  possible sell opportunity"
except:
    fng_value = None
    fng_signal = " Could not fetch Fear & Greed data"

#  PRINT FULL SNAPSHOT 
print("\n" + "="*55)
print(f"   BTC/USDT Market Snapshot  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*55)

print(f"\n   Price:        ${price:,.2f}")

rsi_label = " OVERSOLD" if rsi < 30 else " OVERBOUGHT" if rsi > 70 else " Neutral"
print(f"   RSI:          {rsi:.1f}    {rsi_label}")

macd_label = " Bullish" if macd_val > macd_sig else " Bearish"
print(f"   MACD:         {macd_val:.2f} vs {macd_sig:.2f}    {macd_label}")

if price > bb_upper:
    bb_label = " Above upper band  stretched"
elif price < bb_lower:
    bb_label = " Below lower band  stretched"
else:
    bb_label = " Inside bands  normal"
print(f"   Bollinger:    Upper ${bb_upper:,.0f} | Lower ${bb_lower:,.0f}    {bb_label}")

vol_label = " HIGH  strong move" if volume > vol_avg else " LOW  weak move"
print(f"   Volume:       {volume:,.0f} vs avg {vol_avg:,.0f}    {vol_label}")

if fng_value:
    print(f"   Fear & Greed: {fng_value}/100 ({fng_label})    {fng_signal}")

#  OVERALL SIGNAL 
print("\n" + "-"*55)
bull = sum([
    rsi < 50,
    macd_val > macd_sig,
    price < bb_mid,
    volume > vol_avg,
    fng_value is not None and fng_value < 40
])
total = 5 if fng_value else 4
bear = total - bull

if bull >= 3:
    overall = " BULLISH  more signals point UP"
elif bear >= 3:
    overall = " BEARISH  more signals point DOWN"
else:
    overall = " MIXED  no clear direction yet"

print(f"  Overall signal: {overall}")
print("-"*55)
print("\n Full market snapshot ready for Claude AI!\n")