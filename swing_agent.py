"""
SWING TRADER AGENT
Timeframe : 4h primary + 1D trend confirmation
Stop Loss : 8%
Take Profit: 16%
Position  : 10% of allocated swing capital
Cycle     : every 4 hours

Strategy:
- 1D trend is KING — never fight the daily
- 4H used for entry timing and momentum
- RSI scoring is TREND-AWARE (bull market ≠ bear market RSI thresholds)
- RSI divergence for early reversal detection
- EMA structure + MACD momentum + BB positioning

BUGS FIXED vs previous version:
- BB columns were all wrong (upper/lower swapped, mid off)
- MACD signal line was using histogram (iloc[:,1]) not signal (iloc[:,2])
- RSI zones were flat, not trend-aware — caused sell signals in bull markets
"""

import ccxt
import pandas as pd
import pandas_ta as ta

exchange = ccxt.binance()

STOP_LOSS_PCT   = 0.08   # 8%
TAKE_PROFIT_PCT = 0.16   # 16%
POSITION_SIZE   = 0.10   # 10% of allocated swing capital
CYCLE_SECONDS   = 14400  # 4 hours


class SwingAgent:
    def __init__(self):
        self.name  = "swing"
        self.style = "swing"
        print("✅ Swing Agent initialized")

    def get_data(self, symbol: str) -> dict:
        """Fetch 4h + 1D data and compute all swing indicators."""

        # ── 4H candles ────────────────────────────────────────────
        c4h = exchange.fetch_ohlcv(symbol, "4h", limit=120)
        df4h = pd.DataFrame(c4h, columns=["ts", "open", "high", "low", "close", "volume"])

        df4h["rsi"] = ta.rsi(df4h["close"], length=14)

        macd4h = ta.macd(df4h["close"])
        df4h["macd"]      = macd4h.iloc[:, 0]   # MACD line
        df4h["macd_hist"] = macd4h.iloc[:, 1]   # Histogram
        df4h["macd_sig"]  = macd4h.iloc[:, 2]   # Signal line ← FIXED (was iloc[:,1])

        df4h["ema20"]  = ta.ema(df4h["close"], length=20)
        df4h["ema50"]  = ta.ema(df4h["close"], length=50)
        df4h["ema200"] = ta.ema(df4h["close"], length=min(200, len(df4h) - 1))

        bb4h = ta.bbands(df4h["close"], length=20)
        df4h["bb_lower"] = bb4h.iloc[:, 0]   # BBL ← FIXED (was bb_upper)
        df4h["bb_mid"]   = bb4h.iloc[:, 1]   # BBM ← FIXED (was bb_lower)
        df4h["bb_upper"] = bb4h.iloc[:, 2]   # BBU ← FIXED (was bb_mid)

        df4h["vol_avg"] = df4h["volume"].rolling(20).mean()

        # ── 1D candles ────────────────────────────────────────────
        c1d = exchange.fetch_ohlcv(symbol, "1d", limit=60)
        df1d = pd.DataFrame(c1d, columns=["ts", "open", "high", "low", "close", "volume"])

        df1d["rsi"]   = ta.rsi(df1d["close"], length=14)
        df1d["ema50"] = ta.ema(df1d["close"], length=min(50, len(df1d) - 1))
        df1d["ema200"]= ta.ema(df1d["close"], length=min(200, len(df1d) - 1))

        # ── 1W candles for big-picture context ───────────────────
        try:
            c1w = exchange.fetch_ohlcv(symbol, "1w", limit=30)
            df1w = pd.DataFrame(c1w, columns=["ts", "open", "high", "low", "close", "volume"])
            df1w["ema20"] = ta.ema(df1w["close"], length=min(20, len(df1w) - 1))
            trend_1w = "BULLISH" if float(df1w["close"].iloc[-1]) > float(df1w["ema20"].iloc[-1]) else "BEARISH"
        except Exception:
            trend_1w = "UNKNOWN"

        r4h = df4h.iloc[-1]
        r1d = df1d.iloc[-1]

        # RSI divergence — compare last 4H candle vs 10 candles ago (40 hours)
        lookback = 10
        rsi_prev   = float(df4h["rsi"].iloc[-lookback])   if len(df4h) > lookback else float(r4h["rsi"])
        price_prev = float(df4h["close"].iloc[-lookback]) if len(df4h) > lookback else float(r4h["close"])

        # MACD histogram direction (is swing momentum accelerating?)
        macd_hist_prev = float(df4h["macd_hist"].iloc[-2])
        macd_hist_curr = float(r4h["macd_hist"])

        return {
            "symbol"           : symbol,
            "price"            : float(r4h["close"]),
            "rsi_4h"           : float(r4h["rsi"]),
            "rsi_1d"           : float(r1d["rsi"]),
            "macd"             : float(r4h["macd"]),
            "macd_sig"         : float(r4h["macd_sig"]),
            "macd_hist"        : macd_hist_curr,
            "macd_accelerating": macd_hist_curr > macd_hist_prev,
            "ema20_4h"         : float(r4h["ema20"]),
            "ema50_4h"         : float(r4h["ema50"]),
            "ema200_4h"        : float(r4h["ema200"]),
            "bb_upper"         : float(r4h["bb_upper"]),
            "bb_lower"         : float(r4h["bb_lower"]),
            "bb_mid"           : float(r4h["bb_mid"]),
            "volume"           : float(r4h["volume"]),
            "vol_avg"          : float(r4h["vol_avg"]),
            "trend_4h"         : "BULLISH" if r4h["ema50"] > r4h["ema200"] else "BEARISH",
            "trend_1d"         : "BULLISH" if r1d["ema50"] > r1d["ema200"] else "BEARISH",
            "trend_1w"         : trend_1w,
            "rsi_prev"         : rsi_prev,
            "price_prev"       : price_prev,
        }

    def analyze(self, symbol: str) -> dict:
        print(f"🌊 Swing analyzing {symbol}...")
        try:
            data = self.get_data(symbol)
        except Exception as e:
            print(f"  ⚠️ Swing data error: {e}")
            return self._empty(symbol)

        price      = data["price"]
        rsi_4h     = data["rsi_4h"]
        rsi_1d     = data["rsi_1d"]
        macd       = data["macd"]
        macd_sig   = data["macd_sig"]
        trend_4h   = data["trend_4h"]
        trend_1d   = data["trend_1d"]
        trend_1w   = data["trend_1w"]
        vol_ratio  = data["volume"] / data["vol_avg"] if data["vol_avg"] else 1.0
        is_bull    = trend_1d == "BULLISH"

        score   = 0
        reasons = []

        # ── 1. 1D Trend — KING for swing trading ─────────────────
        if trend_1d == "BULLISH":
            score += 3
            reasons.append("1D trend BULLISH (EMA50 > EMA200) 🟢 — swing with the tide")
        else:
            score -= 3
            reasons.append("1D trend BEARISH (EMA50 < EMA200) 🔴 — swing with the tide")

        # ── 2. 4H Trend — entry timing ───────────────────────────
        if trend_4h == "BULLISH":
            score += 2
            reasons.append("4H trend BULLISH — momentum aligned ✅")
        else:
            score -= 2
            reasons.append("4H trend BEARISH — fighting 4H momentum ⚠️")

        # ── 3. Weekly context bonus ───────────────────────────────
        if trend_1w == trend_1d:
            if trend_1w == "BULLISH":
                score += 1
                reasons.append("1W also BULLISH — full timeframe alignment 💪")
            else:
                score -= 1
                reasons.append("1W also BEARISH — full timeframe alignment 📉")
        elif trend_1w != "UNKNOWN":
            reasons.append(f"1W ({trend_1w}) conflicts with 1D ({trend_1d}) — caution ⚠️")

        # ── 4. RSI — TREND-AWARE (swing zones are wider) ─────────
        if is_bull:
            # Bull market: RSI can stay 50-75 for weeks — that's NORMAL
            if rsi_4h < 30:
                score += 4
                reasons.append(f"4H RSI {rsi_4h:.1f} — major oversold in uptrend, prime entry 🔥")
            elif rsi_4h < 45:
                score += 2
                reasons.append(f"4H RSI {rsi_4h:.1f} — healthy pullback in uptrend 📉➡️📈")
            elif rsi_4h <= 70:
                score += 1
                reasons.append(f"4H RSI {rsi_4h:.1f} — normal uptrend momentum ✅")
            elif rsi_4h <= 82:
                score -= 1
                reasons.append(f"4H RSI {rsi_4h:.1f} — extended but trend intact ⚠️")
            else:
                score -= 3
                reasons.append(f"4H RSI {rsi_4h:.1f} — extremely overbought, reversal risk ❌")
        else:
            # Bear market: RSI can stay 25-55 for weeks — bounces are traps
            if rsi_4h > 70:
                score -= 4
                reasons.append(f"4H RSI {rsi_4h:.1f} — major overbought in downtrend, prime short 🔥")
            elif rsi_4h > 55:
                score -= 2
                reasons.append(f"4H RSI {rsi_4h:.1f} — dead-cat bounce in downtrend 📈➡️📉")
            elif rsi_4h >= 30:
                score -= 1
                reasons.append(f"4H RSI {rsi_4h:.1f} — normal downtrend range ⚠️")
            elif rsi_4h >= 18:
                score += 1
                reasons.append(f"4H RSI {rsi_4h:.1f} — oversold bounce possible")
            else:
                score += 3
                reasons.append(f"4H RSI {rsi_4h:.1f} — extremely oversold, snap-back likely 🟢")

        # ── 5. Daily RSI — big picture extreme ───────────────────
        if rsi_1d < 25:
            score += 3
            reasons.append(f"1D RSI {rsi_1d:.1f} — major daily oversold 🔥")
        elif rsi_1d < 35:
            score += 2
            reasons.append(f"1D RSI {rsi_1d:.1f} — daily oversold zone 🟢")
        elif rsi_1d > 80:
            score -= 3
            reasons.append(f"1D RSI {rsi_1d:.1f} — major daily overbought 🔥")
        elif rsi_1d > 70:
            score -= 2
            reasons.append(f"1D RSI {rsi_1d:.1f} — daily overbought zone 🔴")

        # ── 6. RSI Divergence ─────────────────────────────────────
        price_change = (price - data["price_prev"]) / data["price_prev"] if data["price_prev"] else 0
        rsi_change   = rsi_4h - data["rsi_prev"]

        if price_change > 0.02 and rsi_change < -5:
            score -= 3
            reasons.append("⚠️ Bearish RSI divergence — price up but momentum falling")
        elif price_change < -0.02 and rsi_change > 5:
            score += 3
            reasons.append("✅ Bullish RSI divergence — price down but momentum rising")

        # ── 7. MACD on 4H ────────────────────────────────────────
        if macd > macd_sig:
            if data["macd_accelerating"]:
                score += 2
                reasons.append("4H MACD bullish + accelerating 🚀")
            else:
                score += 1
                reasons.append("4H MACD bullish (momentum fading slightly)")
        else:
            if not data["macd_accelerating"]:
                score -= 2
                reasons.append("4H MACD bearish + decelerating 📉")
            else:
                score -= 1
                reasons.append("4H MACD bearish (momentum recovering slightly)")

        # ── 8. Bollinger Bands on 4H ─────────────────────────────
        bb_range = data["bb_upper"] - data["bb_lower"]
        bb_pct   = (price - data["bb_lower"]) / bb_range if bb_range > 0 else 0.5

        if is_bull:
            if bb_pct < 0.10:
                score += 3
                reasons.append("Price at lower 4H BB in uptrend — high-probability buy zone 💪")
            elif bb_pct < 0.30:
                score += 1
                reasons.append("Price near lower 4H BB — decent swing entry zone")
            elif bb_pct > 0.92:
                score -= 1
                reasons.append("Price at upper 4H BB — slightly stretched (normal in strong trend)")
        else:
            if bb_pct > 0.90:
                score -= 3
                reasons.append("Price at upper 4H BB in downtrend — high-probability sell zone 💪")
            elif bb_pct > 0.70:
                score -= 1
                reasons.append("Price near upper 4H BB — decent short entry zone")
            elif bb_pct < 0.08:
                score += 1
                reasons.append("Price at lower 4H BB — oversold bounce possible")

        # ── 9. EMA structure (stack alignment) ───────────────────
        ema20  = data["ema20_4h"]
        ema50  = data["ema50_4h"]
        ema200 = data["ema200_4h"]

        if price > ema20 > ema50 > ema200:
            score += 2
            reasons.append("Perfect bull stack: Price > EMA20 > EMA50 > EMA200 🏆")
        elif price < ema20 < ema50 < ema200:
            score -= 2
            reasons.append("Perfect bear stack: Price < EMA20 < EMA50 < EMA200 📉")
        elif price > ema50 and ema20 > ema50:
            score += 1
            reasons.append("Price above key EMAs — bullish structure")
        elif price < ema50 and ema20 < ema50:
            score -= 1
            reasons.append("Price below key EMAs — bearish structure")

        # ── 10. Volume confirmation ───────────────────────────────
        if vol_ratio > 1.5:
            score = int(score * 1.25)
            reasons.append(f"Volume {vol_ratio:.1f}x avg — strong conviction 💥")
        elif vol_ratio > 1.2:
            reasons.append(f"Volume {vol_ratio:.1f}x avg — solid confirmation ✅")
        elif vol_ratio < 0.5:
            score = int(score * 0.7)
            reasons.append(f"Volume {vol_ratio:.1f}x avg — weak move, low conviction ⚠️")

        # ── Convert score → signal (swing needs stronger confirmation) ──
        if score >= 7:
            signal, confidence = "BUY", "high"
        elif score >= 4:
            signal, confidence = "BUY", "medium"
        elif score <= -7:
            signal, confidence = "SELL", "high"
        elif score <= -4:
            signal, confidence = "SELL", "medium"
        else:
            signal, confidence = "HOLD", "low"

        print(f"  → {signal} ({confidence}) | score: {score:+d} | 1D={trend_1d} 4H={trend_4h} 1W={trend_1w}")

        return {
            "agent"     : self.name,
            "style"     : self.style,
            "signal"    : signal,
            "confidence": confidence,
            "score"     : score,
            "reasoning" : " | ".join(reasons),
            "raw_data"  : data,
            "sl_pct"    : STOP_LOSS_PCT,
            "tp_pct"    : TAKE_PROFIT_PCT,
            "size_pct"  : POSITION_SIZE,
        }

    def _empty(self, symbol):
        return {
            "agent"     : self.name,
            "style"     : self.style,
            "signal"    : "HOLD",
            "confidence": "low",
            "score"     : 0,
            "reasoning" : "Data error — skipping",
            "raw_data"  : {"symbol": symbol, "price": 0, "trend_4h": "UNKNOWN", "trend_1d": "UNKNOWN"},
            "sl_pct"    : STOP_LOSS_PCT,
            "tp_pct"    : TAKE_PROFIT_PCT,
            "size_pct"  : POSITION_SIZE,
        }


if __name__ == "__main__":
    agent = SwingAgent()
    for sym in ["BTC/USDT", "ETH/USDT"]:
        r = agent.analyze(sym)
        print(f"\nSignal: {r['signal']} ({r['confidence']})")
        print(f"Score:  {r['score']:+d}")
        print(f"Why:    {r['reasoning']}\n")
