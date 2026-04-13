"""
AGENT 1 — Technical Agent
Reads multi-timeframe market data and scores it across
RSI, MACD, Bollinger Bands, Volume, and EMA trend.

Returns a structured dict the Orchestrator can consume.
No LLM used here — deterministic and fast.
"""

import ccxt
import pandas as pd
import pandas_ta as ta

exchange = ccxt.binance()


class TechnicalAgent:
    def __init__(self):
        self.name = "technical"
        print("📊 Technical Agent initialized")

    def get_market_data(self, symbol: str) -> dict:
        """Fetch 1h + 4h candles and compute all indicators."""

        # ── 1H data ─────────────────────────────────────────
        candles_1h = exchange.fetch_ohlcv(symbol, "1h", limit=100)
        df = pd.DataFrame(candles_1h, columns=["timestamp","open","high","low","close","volume"])

        df["rsi"]        = ta.rsi(df["close"], length=14)
        macd             = ta.macd(df["close"])
        df["macd"]       = macd.iloc[:, 0]
        df["macd_sig"]   = macd.iloc[:, 1]
        bb               = ta.bbands(df["close"], length=20)
        df["bb_upper"]   = bb.iloc[:, 0]
        df["bb_lower"]   = bb.iloc[:, 1]
        df["bb_mid"]     = bb.iloc[:, 2]
        df["vol_avg"]    = df["volume"].rolling(20).mean()

        # ── 4H data ─────────────────────────────────────────
        candles_4h = exchange.fetch_ohlcv(symbol, "4h", limit=250)
        df4 = pd.DataFrame(candles_4h, columns=["timestamp","open","high","low","close","volume"])
        df4["rsi"]    = ta.rsi(df4["close"], length=14)
        df4["ema50"]  = ta.ema(df4["close"], length=50)
        df4["ema200"] = ta.ema(df4["close"], length=50)

        r   = df.iloc[-1]
        r4  = df4.iloc[-1]

        return {
            "symbol"   : symbol,
            "price"    : float(r["close"]),
            "rsi"      : float(r["rsi"]),
            "macd"     : float(r["macd"]),
            "macd_sig" : float(r["macd_sig"]),
            "bb_upper" : float(r["bb_upper"]),
            "bb_lower" : float(r["bb_lower"]),
            "bb_mid"   : float(r["bb_mid"]),
            "volume"   : float(r["volume"]),
            "vol_avg"  : float(r["vol_avg"]),
            "rsi_4h"   : float(r4["rsi"]),
            "ema50_4h" : float(r4["ema50"]),
            "ema200_4h": float(r4["ema200"]),
            "trend_4h" : "BULLISH" if r4["ema50"] > r4["ema200"] else "BEARISH",
        }

    def analyze(self, symbol: str) -> dict:
        """
        Score all indicators and return a signal the Orchestrator understands.
        Output: { agent, signal, confidence, score, reasoning, raw_data }
        """
        print(f"📊 Technical Agent analyzing {symbol}...")
        data = self.get_market_data(symbol)

        price     = data["price"]
        rsi       = data["rsi"]
        macd      = data["macd"]
        macd_sig  = data["macd_sig"]
        bb_upper  = data["bb_upper"]
        bb_lower  = data["bb_lower"]
        volume    = data["volume"]
        vol_avg   = data["vol_avg"]
        trend_4h  = data["trend_4h"]
        vol_ratio = volume / vol_avg if vol_avg else 1.0

        score   = 0
        reasons = []

        # ── RSI ──────────────────────────────────────────────
        if rsi < 30:
            score += 3
            reasons.append(f"RSI {rsi:.1f} — deeply oversold 🥶")
        elif rsi < 40:
            score += 1
            reasons.append(f"RSI {rsi:.1f} — leaning oversold")
        elif rsi > 70:
            score -= 3
            reasons.append(f"RSI {rsi:.1f} — deeply overbought 🔥")
        elif rsi > 60:
            score -= 1
            reasons.append(f"RSI {rsi:.1f} — leaning overbought")

        # ── MACD ─────────────────────────────────────────────
        if macd > macd_sig:
            score += 1
            reasons.append("MACD bullish crossover 📈")
        else:
            score -= 1
            reasons.append("MACD bearish crossover 📉")

        # ── Bollinger Bands ──────────────────────────────────
        if price < bb_lower:
            score += 2
            reasons.append("Price below lower BB — oversold stretch")
        elif price > bb_upper:
            score -= 2
            reasons.append("Price above upper BB — overbought stretch")

        # ── Volume confirmation ──────────────────────────────
        if vol_ratio > 1.5:
            score = int(score * 1.4)
            reasons.append(f"Volume {vol_ratio:.1f}x avg — strong conviction 🔊")
        elif vol_ratio < 0.6:
            score = int(score * 0.6)
            reasons.append(f"Volume {vol_ratio:.1f}x avg — weak/unreliable 🔇")

        # ── 4H trend filter ───────────────────────────────────
        if trend_4h == "BULLISH":
            score += 1
            reasons.append("4H trend BULLISH (EMA50 > EMA200) ✅")
        else:
            score -= 1
            reasons.append("4H trend BEARISH (EMA50 < EMA200) ⚠️")

        # ── Convert score → signal ───────────────────────────
        if score >= 4:
            signal, confidence = "BUY", "high"
        elif score >= 2:
            signal, confidence = "BUY", "medium"
        elif score <= -4:
            signal, confidence = "SELL", "high"
        elif score <= -2:
            signal, confidence = "SELL", "medium"
        else:
            signal, confidence = "HOLD", "low"

        result = {
            "agent"      : self.name,
            "signal"     : signal,
            "confidence" : confidence,
            "score"      : score,
            "reasoning"  : " | ".join(reasons),
            "raw_data"   : data,
            "sl_pct"     : 0.03,
            "tp_pct"     : 0.06,
            "size_pct"   : 0.02,
        }

        print(f"  → {signal} ({confidence}) | score: {score:+d}")
        return result


# ── Standalone test ──────────────────────────────────────
if __name__ == "__main__":
    agent = TechnicalAgent()
    result = agent.analyze("BTC/USDT")
    print(f"\nSignal: {result['signal']} ({result['confidence']})")
    print(f"Score:  {result['score']:+d}")
    print(f"Why:    {result['reasoning']}")
