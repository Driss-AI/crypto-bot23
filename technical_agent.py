"""
AGENT 1 — Technical Agent
Reads multi-timeframe market data and scores it across RSI, MACD,
Bollinger Bands, Volume, and EMA trend.

KEY FIX: RSI scoring is now TREND-AWARE.
In a bull market (EMA50 > EMA200), RSI 60-70 is healthy momentum — NOT a sell signal.
In a bear market (EMA50 < EMA200), RSI 40-50 is a dead-cat bounce — NOT a buy signal.

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
        print("✅ Technical Agent initialized")

    def get_market_data(self, symbol: str) -> dict:
        """Fetch 1h + 4h candles and compute all indicators."""

        # ── 1H data ──────────────────────────────────────────────
        candles_1h = exchange.fetch_ohlcv(symbol, "1h", limit=100)
        df = pd.DataFrame(candles_1h, columns=["timestamp", "open", "high", "low", "close", "volume"])

        df["rsi"] = ta.rsi(df["close"], length=14)

        macd = ta.macd(df["close"])
        df["macd"]        = macd.iloc[:, 0]   # MACD line
        df["macd_sig"]    = macd.iloc[:, 2]   # Signal line
        df["macd_hist"]   = macd.iloc[:, 1]   # Histogram (momentum direction)

        bb = ta.bbands(df["close"], length=20)
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_mid"]   = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]

        df["vol_avg"] = df["volume"].rolling(20).mean()

        # ── 4H data ──────────────────────────────────────────────
        candles_4h = exchange.fetch_ohlcv(symbol, "4h", limit=250)
        df4 = pd.DataFrame(candles_4h, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df4["rsi"]    = ta.rsi(df4["close"], length=14)
        df4["ema50"]  = ta.ema(df4["close"], length=50)
        df4["ema200"] = ta.ema(df4["close"], length=200)

        # ── 1D data for big-picture trend ────────────────────────
        candles_1d = exchange.fetch_ohlcv(symbol, "1d", limit=30)
        df1d = pd.DataFrame(candles_1d, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df1d["ema50"]  = ta.ema(df1d["close"], length=50)
        df1d["ema200"] = ta.ema(df1d["close"], length=200)

        r   = df.iloc[-1]
        r4  = df4.iloc[-1]
        r1d = df1d.iloc[-1]

        # MACD histogram direction: is momentum accelerating?
        macd_hist_prev = float(df["macd_hist"].iloc[-2])
        macd_hist_curr = float(r["macd_hist"])
        macd_accelerating = macd_hist_curr > macd_hist_prev

        return {
            "symbol"          : symbol,
            "price"           : float(r["close"]),
            "rsi"             : float(r["rsi"]),
            "macd"            : float(r["macd"]),
            "macd_sig"        : float(r["macd_sig"]),
            "macd_hist"       : macd_hist_curr,
            "macd_accelerating": macd_accelerating,
            "bb_upper"        : float(r["bb_upper"]),
            "bb_lower"        : float(r["bb_lower"]),
            "bb_mid"          : float(r["bb_mid"]),
            "volume"          : float(r["volume"]),
            "vol_avg"         : float(r["vol_avg"]),
            "rsi_4h"          : float(r4["rsi"]),
            "ema50_4h"        : float(r4["ema50"]),
            "ema200_4h"       : float(r4["ema200"]),
            "trend_4h"        : "BULLISH" if r4["ema50"] > r4["ema200"] else "BEARISH",
            "trend_1d"        : "BULLISH" if r1d["ema50"] > r1d["ema200"] else "BEARISH",
        }

    def analyze(self, symbol: str) -> dict:
        print(f"📊 Technical Agent analyzing {symbol}...")
        data    = self.get_market_data(symbol)

        price   = data["price"]
        rsi     = data["rsi"]
        rsi_4h  = data["rsi_4h"]
        macd    = data["macd"]
        macd_sig = data["macd_sig"]
        macd_accelerating = data["macd_accelerating"]
        bb_upper = data["bb_upper"]
        bb_lower = data["bb_lower"]
        volume  = data["volume"]
        vol_avg = data["vol_avg"]
        trend_4h = data["trend_4h"]
        trend_1d = data["trend_1d"]

        is_bull = trend_4h == "BULLISH"
        is_bear = trend_4h == "BEARISH"

        vol_ratio = volume / vol_avg if vol_avg else 1.0
        score = 0
        reasons = []

        # ── 1. RSI — TREND-AWARE ──────────────────────────────────
        # In a bull market: RSI 50-75 is healthy, only extremes matter
        # In a bear market: RSI 30-55 is normal, only extremes matter
        if is_bull:
            if rsi < 30:
                score += 4
                reasons.append(f"RSI {rsi:.1f} deeply oversold in uptrend — strong buy dip 🔥")
            elif rsi < 45:
                score += 2
                reasons.append(f"RSI {rsi:.1f} pullback in uptrend — healthy entry 📉➡️📈")
            elif rsi <= 75:
                score += 1
                reasons.append(f"RSI {rsi:.1f} normal momentum in uptrend ✅")
            elif rsi <= 85:
                score -= 1
                reasons.append(f"RSI {rsi:.1f} extended in uptrend — watch for cooldown ⚠️")
            else:
                score -= 2
                reasons.append(f"RSI {rsi:.1f} extremely overbought even for uptrend ❌")
        else:  # BEARISH trend
            if rsi > 70:
                score -= 4
                reasons.append(f"RSI {rsi:.1f} deeply overbought in downtrend — strong short 🔥")
            elif rsi > 55:
                score -= 2
                reasons.append(f"RSI {rsi:.1f} bounce in downtrend — fade the rally 📈➡️📉")
            elif rsi >= 30:
                score -= 1
                reasons.append(f"RSI {rsi:.1f} normal range in downtrend ⚠️")
            elif rsi >= 20:
                score += 1
                reasons.append(f"RSI {rsi:.1f} oversold bounce potential in downtrend")
            else:
                score += 2
                reasons.append(f"RSI {rsi:.1f} extremely oversold — bounce likely 🟢")

        # ── 2. MACD ───────────────────────────────────────────────
        if macd > macd_sig:
            if macd_accelerating:
                score += 3
                reasons.append("MACD bullish crossover + accelerating momentum 🚀")
            else:
                score += 1
                reasons.append("MACD bullish crossover (momentum fading slightly)")
        else:
            if not macd_accelerating:
                score -= 3
                reasons.append("MACD bearish crossover + momentum declining 📉")
            else:
                score -= 1
                reasons.append("MACD bearish but momentum recovering slightly")

        # ── 3. Bollinger Bands ────────────────────────────────────
        bb_range = bb_upper - bb_lower
        bb_pct   = (price - bb_lower) / bb_range if bb_range > 0 else 0.5

        if is_bull:
            if bb_pct < 0.15:
                score += 3
                reasons.append("Price at lower BB in uptrend — mean reversion buy 💪")
            elif bb_pct < 0.35:
                score += 1
                reasons.append("Price near lower BB in uptrend — mild buy signal")
            elif bb_pct > 0.90:
                score -= 1
                reasons.append("Price at upper BB — slightly extended (normal in strong trend)")
        else:  # BEARISH
            if bb_pct > 0.85:
                score -= 3
                reasons.append("Price at upper BB in downtrend — mean reversion sell 💪")
            elif bb_pct > 0.65:
                score -= 1
                reasons.append("Price near upper BB in downtrend — mild sell signal")
            elif bb_pct < 0.10:
                score += 1
                reasons.append("Price at lower BB — slightly oversold (bounce possible)")

        # ── 4. Volume confirmation ────────────────────────────────
        if vol_ratio > 1.5:
            score = int(score * 1.3)
            reasons.append(f"Volume {vol_ratio:.1f}x avg — strong conviction 💥")
        elif vol_ratio > 1.2:
            reasons.append(f"Volume {vol_ratio:.1f}x avg — above average ✅")
        elif vol_ratio < 0.6:
            score = int(score * 0.6)
            reasons.append(f"Volume {vol_ratio:.1f}x avg — weak/unreliable ⚠️")
        else:
            reasons.append(f"Volume {vol_ratio:.1f}x avg — normal")

        # ── 5. 4H trend alignment ─────────────────────────────────
        if trend_4h == "BULLISH":
            score += 2
            reasons.append("4H trend BULLISH (EMA50 > EMA200) 🟢")
        else:
            score -= 2
            reasons.append("4H trend BEARISH (EMA50 < EMA200) 🔴")

        # ── 6. 1D trend alignment (bonus filter) ─────────────────
        if trend_1d == "BULLISH" and trend_4h == "BULLISH":
            score += 1
            reasons.append("1D trend also BULLISH — strong alignment 💪")
        elif trend_1d == "BEARISH" and trend_4h == "BEARISH":
            score -= 1
            reasons.append("1D trend also BEARISH — strong alignment 📉")
        elif trend_1d != trend_4h:
            reasons.append(f"1D ({trend_1d}) vs 4H ({trend_4h}) conflicting — caution ⚠️")

        # ── Convert score → signal ────────────────────────────────
        # Symmetric thresholds — equal burden to BUY or SELL
        if score >= 5:
            signal, confidence = "BUY", "high"
        elif score >= 2:
            signal, confidence = "BUY", "medium"
        elif score <= -5:
            signal, confidence = "SELL", "high"
        elif score <= -2:
            signal, confidence = "SELL", "medium"
        else:
            signal, confidence = "HOLD", "low"

        result = {
            "agent"     : self.name,
            "signal"    : signal,
            "confidence": confidence,
            "score"     : score,
            "reasoning" : " | ".join(reasons),
            "raw_data"  : data,
            # Day trade params (swing_agent overrides these for swing)
            "sl_pct"    : 0.03,
            "tp_pct"    : 0.06,
            "size_pct"  : 0.02,
        }

        print(f"  → {signal} ({confidence}) | score: {score:+d} | trend: {trend_4h}")
        return result


if __name__ == "__main__":
    agent = TechnicalAgent()
    for sym in ["BTC/USDT", "ETH/USDT"]:
        result = agent.analyze(sym)
        print(f"\nSignal: {result['signal']} ({result['confidence']})")
        print(f"Score:  {result['score']:+d}")
        print(f"Why:    {result['reasoning']}\n")
