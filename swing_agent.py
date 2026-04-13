"""
SWING TRADER AGENT
═══════════════════════════════════════════════════
Timeframe : 4h + 1d confirmation
Stop Loss : 8%
Take Profit: 16%
Position  : 1% of capital
Cycle     : every 4 hours

Looks for:
- Major trend changes on 4h
- 1D support/resistance levels
- RSI divergence
- EMA crossovers on 4h
- Big picture macro alignment
"""

import ccxt
import pandas as pd
import pandas_ta as ta

exchange = ccxt.binance()

STOP_LOSS_PCT    = 0.08    # 8%
TAKE_PROFIT_PCT  = 0.16    # 16%
POSITION_SIZE    = 0.10    # 10% of capital
CYCLE_SECONDS    = 14400   # 4 hours


class SwingAgent:
    def __init__(self):
        self.name  = "swing"
        self.style = "swing"
        print("🌊 Swing Agent initialized")

    def get_data(self, symbol: str) -> dict:
        # 4h candles — main timeframe
        c4h = exchange.fetch_ohlcv(symbol, "4h", limit=100)
        # 1d candles — trend confirmation
        c1d = exchange.fetch_ohlcv(symbol, "1d", limit=50)

        df4h = pd.DataFrame(c4h, columns=["ts","open","high","low","close","volume"])
        df1d = pd.DataFrame(c1d, columns=["ts","open","high","low","close","volume"])

        # 4h indicators
        df4h["rsi"]      = ta.rsi(df4h["close"], length=14)
        macd             = ta.macd(df4h["close"])
        df4h["macd"]     = macd.iloc[:, 0]
        df4h["macd_sig"] = macd.iloc[:, 1]
        df4h["ema20"]    = ta.ema(df4h["close"], length=20)
        df4h["ema50"]    = ta.ema(df4h["close"], length=50)
        df4h["ema200"]   = ta.ema(df4h["close"], length=min(200, len(df4h)-1))
        bb               = ta.bbands(df4h["close"], length=20)
        df4h["bb_upper"] = bb.iloc[:, 0]
        df4h["bb_lower"] = bb.iloc[:, 1]
        df4h["bb_mid"]   = bb.iloc[:, 2]
        df4h["vol_avg"]  = df4h["volume"].rolling(20).mean()

        # 1d indicators
        df1d["rsi"]      = ta.rsi(df1d["close"], length=14)
        df1d["ema50"]    = ta.ema(df1d["close"], length=min(50, len(df1d)-1))
        df1d["ema200"]   = ta.ema(df1d["close"], length=min(200, len(df1d)-1))

        r4h = df4h.iloc[-1]
        r1d = df1d.iloc[-1]

        # RSI divergence — compare current vs 10 candles ago
        rsi_prev = float(df4h["rsi"].iloc[-10]) if len(df4h) > 10 else float(r4h["rsi"])
        price_prev = float(df4h["close"].iloc[-10]) if len(df4h) > 10 else float(r4h["close"])

        return {
            "symbol"      : symbol,
            "price"       : float(r4h["close"]),
            "rsi_4h"      : float(r4h["rsi"]),
            "rsi_1d"      : float(r1d["rsi"]),
            "macd"        : float(r4h["macd"]),
            "macd_sig"    : float(r4h["macd_sig"]),
            "ema20_4h"    : float(r4h["ema20"]),
            "ema50_4h"    : float(r4h["ema50"]),
            "ema200_4h"   : float(r4h["ema200"]),
            "bb_upper"    : float(r4h["bb_upper"]),
            "bb_lower"    : float(r4h["bb_lower"]),
            "bb_mid"      : float(r4h["bb_mid"]),
            "volume"      : float(r4h["volume"]),
            "vol_avg"     : float(r4h["vol_avg"]),
            "trend_4h"    : "BULLISH" if r4h["ema50"] > r4h["ema200"] else "BEARISH",
            "trend_1d"    : "BULLISH" if r1d["ema50"] > r1d["ema200"] else "BEARISH",
            "rsi_prev"    : rsi_prev,
            "price_prev"  : price_prev,
        }

    def analyze(self, symbol: str) -> dict:
        print(f"  🌊 Swing analyzing {symbol}...")
        try:
            data = self.get_data(symbol)
        except Exception as e:
            print(f"  ⚠️ Swing data error: {e}")
            return self._empty(symbol)

        price    = data["price"]
        rsi_4h   = data["rsi_4h"]
        rsi_1d   = data["rsi_1d"]
        macd     = data["macd"]
        macd_sig = data["macd_sig"]
        trend_4h = data["trend_4h"]
        trend_1d = data["trend_1d"]
        vol_ratio = data["volume"] / data["vol_avg"] if data["vol_avg"] else 1.0

        score   = 0
        reasons = []

        # 1D trend is king for swing trading
        if trend_1d == "BULLISH":
            score += 2
            reasons.append("1D trend BULLISH ✅ (EMA50 > EMA200)")
        else:
            score -= 2
            reasons.append("1D trend BEARISH ⚠️ (EMA50 < EMA200)")

        # 4H trend confirmation
        if trend_4h == "BULLISH":
            score += 1
            reasons.append("4H trend BULLISH")
        else:
            score -= 1
            reasons.append("4H trend BEARISH")

        # RSI on 4h — wider zones for swing
        if rsi_4h < 35:
            score += 2
            reasons.append(f"4H RSI {rsi_4h:.1f} — oversold")
        elif rsi_4h > 65:
            score -= 2
            reasons.append(f"4H RSI {rsi_4h:.1f} — overbought")

        # Daily RSI extreme
        if rsi_1d < 30:
            score += 2
            reasons.append(f"1D RSI {rsi_1d:.1f} — major oversold 🔥")
        elif rsi_1d > 70:
            score -= 2
            reasons.append(f"1D RSI {rsi_1d:.1f} — major overbought")

        # RSI divergence (price up but RSI down = bearish divergence)
        price_change = (price - data["price_prev"]) / data["price_prev"]
        rsi_change   = rsi_4h - data["rsi_prev"]
        if price_change > 0.02 and rsi_change < -5:
            score -= 2
            reasons.append("Bearish RSI divergence ⚠️")
        elif price_change < -0.02 and rsi_change > 5:
            score += 2
            reasons.append("Bullish RSI divergence 💡")

        # MACD on 4h
        if macd > macd_sig:
            score += 1
            reasons.append("4H MACD bullish")
        else:
            score -= 1
            reasons.append("4H MACD bearish")

        # Bollinger on 4h
        if price < data["bb_lower"]:
            score += 1
            reasons.append("4H price below lower BB")
        elif price > data["bb_upper"]:
            score -= 1
            reasons.append("4H price above upper BB")

        # Convert — swing needs stronger signal (higher threshold)
        if score >= 5:
            signal, confidence = "BUY", "high"
        elif score >= 3:
            signal, confidence = "BUY", "medium"
        elif score <= -5:
            signal, confidence = "SELL", "high"
        elif score <= -3:
            signal, confidence = "SELL", "medium"
        else:
            signal, confidence = "HOLD", "low"

        print(f"    → {signal} ({confidence}) | score: {score:+d}")
        return {
            "agent"      : self.name,
            "style"      : self.style,
            "signal"     : signal,
            "confidence" : confidence,
            "score"      : score,
            "reasoning"  : " | ".join(reasons),
            "raw_data"   : data,
            "sl_pct"     : STOP_LOSS_PCT,
            "tp_pct"     : TAKE_PROFIT_PCT,
            "size_pct"   : POSITION_SIZE,
        }

    def _empty(self, symbol):
        return {"agent": self.name, "style": self.style,
                "signal": "HOLD", "confidence": "low",
                "score": 0, "reasoning": "Data error",
                "raw_data": {"symbol": symbol, "price": 0},
                "sl_pct": STOP_LOSS_PCT, "tp_pct": TAKE_PROFIT_PCT,
                "size_pct": POSITION_SIZE}


if __name__ == "__main__":
    agent = SwingAgent()
    r = agent.analyze("BTC/USDT")
    print(f"\nSignal: {r['signal']} ({r['confidence']})")
    print(f"Why:    {r['reasoning']}")
