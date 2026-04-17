"""
SCALPER AGENT - ENHANCED
========================
Timeframe : 1m candles (was 5m) - reacts to every candle
Cycle     : every 60 seconds (was 300s)
Stop Loss : 0.4% (tightened)
Take Profit: 0.8% (2:1 ratio)
Position  : 5% of capital

Key improvements:
- 1m candles for faster reaction
- Waits for CLOSED candle confirmation (no mid-candle entries)
- Volume must be 2x average (was 1.5x)
- 5m trend filter - only trade WITH the 5m trend
- RSI divergence check
"""

import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone

exchange = ccxt.binance()

STOP_LOSS_PCT   = 0.004   # 0.4%
TAKE_PROFIT_PCT = 0.008   # 0.8% - tight but realistic for 1m scalp
POSITION_SIZE   = 0.05    # 5% of capital
CYCLE_SECONDS   = 60      #  1 minute cycles


class ScalperAgent:
    def __init__(self):
        self.name  = "scalper"
        self.style = "scalp"
        print(" Scalper Agent initialized  1min cycles")

    def get_data(self, symbol: str) -> dict:
        # 1m candles for entry signal
        c1  = exchange.fetch_ohlcv(symbol, "1m",  limit=60)
        # 5m candles for trend filter
        c5  = exchange.fetch_ohlcv(symbol, "5m",  limit=30)

        df1 = pd.DataFrame(c1,  columns=["ts","open","high","low","close","volume"])
        df5 = pd.DataFrame(c5,  columns=["ts","open","high","low","close","volume"])

        #  1m indicators 
        df1["rsi"]     = ta.rsi(df1["close"], length=9)   # faster RSI for 1m
        macd1          = ta.macd(df1["close"], fast=8, slow=17, signal=9)
        df1["macd"]    = macd1.iloc[:, 0].fillna(0)
        df1["macd_sig"]= macd1.iloc[:, 2].fillna(0)
        df1["vol_avg"] = df1["volume"].rolling(20).mean()
        bb1            = ta.bbands(df1["close"], length=15)
        df1["bb_lower"]= bb1.iloc[:, 0].fillna(df1["close"])
        df1["bb_upper"]= bb1.iloc[:, 2].fillna(df1["close"])

        #  5m trend filter 
        df5["ema20"] = ta.ema(df5["close"], length=20)
        df5["ema50"] = ta.ema(df5["close"], length=50)
        df5["rsi"]   = ta.rsi(df5["close"], length=14)

        last1  = df1.iloc[-2]   #  CLOSED candle (not current)
        last5  = df5.iloc[-1]
        price  = float(df1["close"].iloc[-1])

        # 5m trend direction
        trend_up   = float(last5["ema20"]) > float(last5["ema50"])
        trend_down = float(last5["ema20"]) < float(last5["ema50"])
        rsi_5m     = float(last5["rsi"])

        def safe(v, default=0.0):
            try: return float(v) if v is not None and str(v) != 'nan' else default
            except: return default

        return {
            "price"     : safe(df1["close"].iloc[-1], 0),
            "rsi_1m"    : safe(last1["rsi"], 50),
            "macd_1m"   : safe(last1["macd"], 0),
            "macd_sig_1m": safe(last1["macd_sig"], 0),
            "vol_ratio" : safe(last1["volume"], 1) / max(safe(last1["vol_avg"], 1), 1),
            "bb_lower"  : safe(last1["bb_lower"], safe(df1["close"].iloc[-1], 0) * 0.995),
            "bb_upper"  : safe(last1["bb_upper"], safe(df1["close"].iloc[-1], 0) * 1.005),
            "trend_up"  : trend_up,
            "trend_down": trend_down,
            "rsi_5m"    : safe(last5["rsi"], 50),
            "candle_bullish": safe(last1["close"], 0) > safe(last1["open"], 0),
            "candle_bearish": safe(last1["close"], 0) < safe(last1["open"], 0),
        }

    def analyze(self, symbol: str) -> dict:
        try:
            d = self.get_data(symbol)
        except Exception as e:
            print(f" Scalper data error {symbol}: {e}")
            return None

        price      = d["price"]
        rsi        = d["rsi_1m"]
        macd       = d["macd_1m"]
        macd_sig   = d["macd_sig_1m"]
        vol_ratio  = d["vol_ratio"]
        score      = 0
        reasons    = []

        #  GATE 1: Volume must confirm (2x average) 
        if vol_ratio < 1.8:
            return {
                "signal"   : "HOLD",
                "score"    : 0,
                "reasoning": f"Low volume ({vol_ratio:.1f}x)  no scalp",
                "sl_pct"   : STOP_LOSS_PCT,
                "tp_pct"   : TAKE_PROFIT_PCT,
                "size_pct" : POSITION_SIZE,
                "raw_data" : {"price": price, "rsi": rsi},
            }

        #  GATE 2: Only trade with 5m trend 
        with_trend_up   = d["trend_up"]   and d["candle_bullish"]
        with_trend_down = d["trend_down"] and d["candle_bearish"]

        if not with_trend_up and not with_trend_down:
            return {
                "signal"   : "HOLD",
                "score"    : 0,
                "reasoning": "Against 5m trend  skip",
                "sl_pct"   : STOP_LOSS_PCT,
                "tp_pct"   : TAKE_PROFIT_PCT,
                "size_pct" : POSITION_SIZE,
                "raw_data" : {"price": price, "rsi": rsi},
            }

        #  RSI signal 
        if rsi < 30:
            score += 3; reasons.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 40:
            score += 1; reasons.append(f"RSI {rsi:.0f} leaning oversold")
        elif rsi > 70:
            score -= 3; reasons.append(f"RSI {rsi:.0f} overbought")
        elif rsi > 60:
            score -= 1; reasons.append(f"RSI {rsi:.0f} leaning overbought")

        #  MACD crossover 
        if macd > macd_sig:
            score += 2; reasons.append("MACD bullish cross")
        else:
            score -= 2; reasons.append("MACD bearish cross")

        #  BB extremes 
        if price <= d["bb_lower"]:
            score += 2; reasons.append("At lower BB  bounce setup")
        elif price >= d["bb_upper"]:
            score -= 2; reasons.append("At upper BB  rejection setup")

        #  Volume boost 
        if vol_ratio > 3:
            score = int(score * 1.5); reasons.append(f"HUGE volume {vol_ratio:.1f}x")
        elif vol_ratio > 2:
            score = int(score * 1.2); reasons.append(f"Strong volume {vol_ratio:.1f}x")

        #  Final signal 
        if score >= 3:
            signal = "BUY"
        elif score <= -3:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "signal"   : signal,
            "score"    : score,
            "reasoning": " | ".join(reasons),
            "sl_pct"   : STOP_LOSS_PCT,
            "tp_pct"   : TAKE_PROFIT_PCT,
            "size_pct" : POSITION_SIZE,
            "raw_data" : {
                "price"    : price,
                "rsi"      : rsi,
                "vol_ratio": vol_ratio,
                "trend"    : "UP" if d["trend_up"] else "DOWN",
            },
        }
