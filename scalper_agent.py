"""
SCALPER AGENT
═══════════════════════════════════════════════════
Timeframe : 5m + 15m confirmation
Stop Loss : 0.5%
Take Profit: 1.0%
Position  : 5% of capital
Cycle     : every 5 minutes

Looks for:
- RSI extremes on 5m
- MACD crossover on 5m
- Volume spike confirmation
- 15m trend not against us
"""

import ccxt
import pandas as pd
import pandas_ta as ta

exchange = ccxt.binance()

STOP_LOSS_PCT    = 0.005   # 0.5%
TAKE_PROFIT_PCT  = 0.010   # 1.0%
POSITION_SIZE    = 0.05    # 5% of capital
CYCLE_SECONDS    = 300     # 5 minutes


class ScalperAgent:
    def __init__(self):
        self.name  = "scalper"
        self.style = "scalp"
        print("🔥 Scalper Agent initialized")

    def get_data(self, symbol: str) -> dict:
        # 5m candles
        c5  = exchange.fetch_ohlcv(symbol, "5m",  limit=50)
        # 15m for trend confirmation
        c15 = exchange.fetch_ohlcv(symbol, "15m", limit=30)

        df5  = pd.DataFrame(c5,  columns=["ts","open","high","low","close","volume"])
        df15 = pd.DataFrame(c15, columns=["ts","open","high","low","close","volume"])

        # 5m indicators
        df5["rsi"]     = ta.rsi(df5["close"], length=7)    # shorter RSI for scalping
        macd           = ta.macd(df5["close"], fast=8, slow=17, signal=9)
        df5["macd"]    = macd.iloc[:, 0]
        df5["macd_sig"]= macd.iloc[:, 1]
        bb             = ta.bbands(df5["close"], length=10) # tighter BB
        df5["bb_upper"]= bb.iloc[:, 0]
        df5["bb_lower"]= bb.iloc[:, 1]
        df5["bb_mid"]  = bb.iloc[:, 2]
        df5["vol_avg"] = df5["volume"].rolling(10).mean()

        # 15m trend
        df15["ema20"]  = ta.ema(df15["close"], length=min(20, len(df15)-1))
        df15["ema50"]  = ta.ema(df15["close"], length=min(50, len(df15)-1))

        r5  = df5.iloc[-1]
        r15 = df15.iloc[-1]

        return {
            "symbol"    : symbol,
            "price"     : float(r5["close"]),
            "rsi"       : float(r5["rsi"]),
            "macd"      : float(r5["macd"]),
            "macd_sig"  : float(r5["macd_sig"]),
            "bb_upper"  : float(r5["bb_upper"]),
            "bb_lower"  : float(r5["bb_lower"]),
            "bb_mid"    : float(r5["bb_mid"]),
            "volume"    : float(r5["volume"]),
            "vol_avg"   : float(r5["vol_avg"]),
            "trend_15m" : "BULLISH" if r15["ema20"] > r15["ema50"] else "BEARISH",
        }

    def analyze(self, symbol: str) -> dict:
        print(f"  🔥 Scalper analyzing {symbol}...")
        try:
            data = self.get_data(symbol)
        except Exception as e:
            print(f"  ⚠️ Scalper data error: {e}")
            return self._empty(symbol)

        price     = data["price"]
        rsi       = data["rsi"]
        macd      = data["macd"]
        macd_sig  = data["macd_sig"]
        bb_upper  = data["bb_upper"]
        bb_lower  = data["bb_lower"]
        volume    = data["volume"]
        vol_avg   = data["vol_avg"]
        trend_15m = data["trend_15m"]
        vol_ratio = volume / vol_avg if vol_avg else 1.0

        score   = 0
        reasons = []

        # RSI — tighter thresholds for scalping
        if rsi < 25:
            score += 3
            reasons.append(f"RSI {rsi:.1f} — deeply oversold 🥶")
        elif rsi < 35:
            score += 1
            reasons.append(f"RSI {rsi:.1f} — oversold")
        elif rsi > 75:
            score -= 3
            reasons.append(f"RSI {rsi:.1f} — deeply overbought 🔥")
        elif rsi > 65:
            score -= 1
            reasons.append(f"RSI {rsi:.1f} — overbought")

        # MACD crossover
        if macd > macd_sig:
            score += 1
            reasons.append("MACD bullish 📈")
        else:
            score -= 1
            reasons.append("MACD bearish 📉")

        # Bollinger — price at extremes
        if price < bb_lower:
            score += 2
            reasons.append("Price below lower BB — bounce opportunity")
        elif price > bb_upper:
            score -= 2
            reasons.append("Price above upper BB — reversal risk")

        # Volume must confirm for scalping
        if vol_ratio > 1.5:
            score = int(score * 1.5)
            reasons.append(f"Volume {vol_ratio:.1f}x — strong 🔊")
        elif vol_ratio < 0.8:
            score = int(score * 0.5)   # heavily dampen low volume scalps
            reasons.append(f"Volume {vol_ratio:.1f}x — too weak, dampening signal 🔇")

        # 15m trend filter — don't scalp against the trend
        if trend_15m == "BEARISH" and score > 0:
            score = max(score - 2, 0)
            reasons.append("15m trend BEARISH — reducing buy signal")
        elif trend_15m == "BULLISH" and score < 0:
            score = min(score + 2, 0)
            reasons.append("15m trend BULLISH — reducing sell signal")

        # Convert
        if score >= 3:
            signal, confidence = "BUY", "high"
        elif score >= 1:
            signal, confidence = "BUY", "medium"
        elif score <= -3:
            signal, confidence = "SELL", "high"
        elif score <= -1:
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
    agent = ScalperAgent()
    r = agent.analyze("BTC/USDT")
    print(f"\nSignal: {r['signal']} ({r['confidence']})")
    print(f"Why:    {r['reasoning']}")
