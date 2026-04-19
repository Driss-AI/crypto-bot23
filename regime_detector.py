"""
REGIME DETECTOR
Classifies current market regime before any trade signal is considered.

Regime gates the entire system:
- CHOP     → no trades at all (biggest single performance improvement)
- RANGING  → swing only, tighter thresholds
- TRENDING_UP / TRENDING_DOWN → full system active

Detection uses three independent signals that must agree (2 of 3):
1. ADX strength    — is there a trend at all?
2. EMA structure   — what direction?
3. ATR volatility  — is it a real move or noise?
"""

import ccxt
import pandas as pd
import pandas_ta as ta

exchange = ccxt.binance()


class RegimeDetector:

    REGIMES = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "CHOP"]

    def __init__(self):
        self.name = "regime"
        print("✅ Regime Detector initialized")

    def get_data(self, symbol: str) -> dict:
        """4H + 1D data for regime classification."""
        c4h = exchange.fetch_ohlcv(symbol, "4h", limit=60)
        df = pd.DataFrame(c4h, columns=["ts", "open", "high", "low", "close", "volume"])

        # ADX (trend strength — regime-agnostic)
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
        df["adx"]   = adx_df.iloc[:, 0]   # ADX value
        df["di_pos"] = adx_df.iloc[:, 1]  # +DI
        df["di_neg"] = adx_df.iloc[:, 2]  # -DI

        # EMAs (trend direction)
        df["ema20"]  = ta.ema(df["close"], length=20)
        df["ema50"]  = ta.ema(df["close"], length=50)

        # ATR (volatility — distinguishes real moves from noise)
        df["atr"]     = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["atr_pct"] = df["atr"] / df["close"] * 100

        # 1D EMA for big-picture direction
        c1d = exchange.fetch_ohlcv(symbol, "1d", limit=30)
        df1d = pd.DataFrame(c1d, columns=["ts", "open", "high", "low", "close", "volume"])
        df1d["ema50"]  = ta.ema(df1d["close"], length=min(50, len(df1d) - 1))
        df1d["ema200"] = ta.ema(df1d["close"], length=min(200, len(df1d) - 1))

        r   = df.iloc[-1]
        r1d = df1d.iloc[-1]

        # ATR percentile vs last 30 bars (is current volatility normal or extreme?)
        atr_history    = df["atr_pct"].dropna().tail(30)
        atr_percentile = (atr_history < float(r["atr_pct"])).mean()

        return {
            "price"         : float(r["close"]),
            "adx"           : float(r["adx"]),
            "di_pos"        : float(r["di_pos"]),
            "di_neg"        : float(r["di_neg"]),
            "ema20_4h"      : float(r["ema20"]),
            "ema50_4h"      : float(r["ema50"]),
            "atr_pct"       : float(r["atr_pct"]),
            "atr_percentile": atr_percentile,   # 0-1, higher = more volatile than usual
            "ema50_1d"      : float(r1d["ema50"]),
            "ema200_1d"     : float(r1d["ema200"]),
            "trend_1d"      : "UP" if r1d["ema50"] > r1d["ema200"] else "DOWN",
        }

    def classify(self, symbol: str) -> dict:
        """
        Classify regime. Returns dict with regime + supporting data.

        Decision logic (2-of-3 vote):
          Signal A — ADX: < 15 = no trend, 15-25 = weak, > 25 = trending
          Signal B — EMA: price vs EMA20 vs EMA50 alignment
          Signal C — ATR: too low = chop, too high = whipsaw danger
        """
        try:
            d = self.get_data(symbol)
        except Exception as e:
            print(f"  ⚠️ Regime detection error for {symbol}: {e}")
            return self._default()

        adx          = d["adx"]
        di_pos       = d["di_pos"]
        di_neg       = d["di_neg"]
        price        = d["price"]
        ema20        = d["ema20_4h"]
        ema50        = d["ema50_4h"]
        atr_pct      = d["atr_pct"]
        atr_pctile   = d["atr_percentile"]
        trend_1d     = d["trend_1d"]

        votes     = []
        reasons   = []

        # ── Signal A: ADX strength ────────────────────────────────
        if adx < 15:
            votes.append("CHOP")
            reasons.append(f"ADX {adx:.1f} < 15 — no trend 🔴")
        elif adx < 22:
            votes.append("RANGING")
            reasons.append(f"ADX {adx:.1f} = weak trend ⚠️")
        else:
            # Strong trend — direction from DI lines
            if di_pos > di_neg:
                votes.append("TRENDING_UP")
                reasons.append(f"ADX {adx:.1f} strong + +DI dominates → UP 🟢")
            else:
                votes.append("TRENDING_DOWN")
                reasons.append(f"ADX {adx:.1f} strong + -DI dominates → DOWN 🔴")

        # ── Signal B: EMA structure ───────────────────────────────
        ema_spread_pct = abs(ema20 - ema50) / ema50 * 100

        if ema_spread_pct < 0.3:
            votes.append("CHOP")
            reasons.append(f"EMA20≈EMA50 (spread {ema_spread_pct:.2f}%) — compression 🔴")
        elif price > ema20 > ema50:
            votes.append("TRENDING_UP")
            reasons.append("Price > EMA20 > EMA50 — bull stack ✅")
        elif price < ema20 < ema50:
            votes.append("TRENDING_DOWN")
            reasons.append("Price < EMA20 < EMA50 — bear stack ✅")
        else:
            votes.append("RANGING")
            reasons.append("Mixed EMA structure — ranging ⚠️")

        # ── Signal C: ATR / Volatility ────────────────────────────
        if atr_pct < 0.4:
            votes.append("CHOP")
            reasons.append(f"ATR {atr_pct:.2f}% — very low volatility 🔴")
        elif atr_pctile > 0.90:
            # Extreme volatility — dangerous for entries, treat as ranging
            votes.append("RANGING")
            reasons.append(f"ATR at 90th+ percentile — whipsaw risk ⚠️")
        else:
            # Normal volatility — follow EMA vote
            votes.append(votes[1])  # mirror Signal B
            reasons.append(f"ATR {atr_pct:.2f}% — normal volatility ✅")

        # ── 2-of-3 majority vote ──────────────────────────────────
        from collections import Counter
        vote_counts = Counter(votes)
        winner      = vote_counts.most_common(1)[0][0]

        # 1D trend override: if 1D says DOWN but we voted TRENDING_UP → downgrade to RANGING
        if winner == "TRENDING_UP" and trend_1d == "DOWN":
            winner = "RANGING"
            reasons.append("⚠️ 1D trend BEARISH — downgraded UP→RANGING")
        elif winner == "TRENDING_DOWN" and trend_1d == "UP":
            winner = "RANGING"
            reasons.append("⚠️ 1D trend BULLISH — downgraded DOWN→RANGING")

        result = {
            "regime"        : winner,
            "votes"         : votes,
            "adx"           : adx,
            "atr_pct"       : atr_pct,
            "trend_1d"      : trend_1d,
            "tradeable"     : winner != "CHOP",
            "swing_ok"      : winner in ("TRENDING_UP", "TRENDING_DOWN", "RANGING"),
            "day_ok"        : winner in ("TRENDING_UP", "TRENDING_DOWN"),
            "reasons"       : reasons,
        }

        emoji = {"TRENDING_UP": "🟢", "TRENDING_DOWN": "🔴", "RANGING": "🟡", "CHOP": "⛔"}
        print(f"  📊 Regime [{symbol}]: {emoji.get(winner, '')} {winner} | ADX={adx:.1f} ATR={atr_pct:.2f}%")
        return result

    def _default(self):
        return {
            "regime"   : "RANGING",
            "votes"    : [],
            "adx"      : 0,
            "atr_pct"  : 0,
            "trend_1d" : "UNKNOWN",
            "tradeable": True,
            "swing_ok" : True,
            "day_ok"   : False,
            "reasons"  : ["Data error — defaulting to RANGING"],
        }


if __name__ == "__main__":
    det = RegimeDetector()
    for sym in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
        r = det.classify(sym)
        print(f"\nRegime: {r['regime']}")
        print(f"Tradeable: {r['tradeable']} | Day OK: {r['day_ok']} | Swing OK: {r['swing_ok']}")
        print(f"Reasons: {' | '.join(r['reasons'])}\n")
