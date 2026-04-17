"""
SCALPER AGENT - Bulletproof version
1m candles, simple logic, no complex indicator chains
"""
import ccxt
import pandas as pd

exchange = ccxt.binance()

STOP_LOSS_PCT   = 0.004
TAKE_PROFIT_PCT = 0.008
POSITION_SIZE   = 0.05


class ScalperAgent:
    def __init__(self):
        self.name  = "scalper"
        self.style = "scalp"
        print("Scalper Agent initialized - 1min cycles")

    def analyze(self, symbol: str) -> dict:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, "1m", limit=50)
            if not ohlcv or len(ohlcv) < 20:
                return self._hold("Not enough data")

            closes  = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            price   = closes[-1]
            prev_closes = closes[:-1]
            prev_vols   = volumes[:-1]

            gains, losses = [], []
            for i in range(1, len(prev_closes)):
                diff = prev_closes[i] - prev_closes[i-1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))

            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            rsi = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

            vol_avg   = sum(prev_vols[-20:]) / 20
            vol_ratio = prev_vols[-1] / vol_avg if vol_avg > 0 else 1

            trend_up   = prev_closes[-1] > prev_closes[-5]
            trend_down = prev_closes[-1] < prev_closes[-5]
            bull_candle = prev_closes[-1] > ohlcv[-2][1]
            bear_candle = prev_closes[-1] < ohlcv[-2][1]

            if vol_ratio < 1.5:
                return self._hold(f"Low volume {vol_ratio:.1f}x")

            score, reasons = 0, []

            if rsi < 35:
                score += 3; reasons.append(f"RSI {rsi:.0f} oversold")
            elif rsi < 45:
                score += 1; reasons.append(f"RSI {rsi:.0f} low")
            elif rsi > 65:
                score -= 3; reasons.append(f"RSI {rsi:.0f} overbought")
            elif rsi > 55:
                score -= 1; reasons.append(f"RSI {rsi:.0f} high")

            if trend_up and bull_candle:
                score += 2; reasons.append("Trend up + bull candle")
            elif trend_down and bear_candle:
                score -= 2; reasons.append("Trend down + bear candle")

            if vol_ratio > 3:
                score = int(score * 1.5); reasons.append(f"Strong volume {vol_ratio:.1f}x")

            signal = "BUY" if score >= 3 else "SELL" if score <= -3 else "HOLD"

            return {
                "signal"   : signal,
                "score"    : score,
                "reasoning": " | ".join(reasons) or "No strong signal",
                "sl_pct"   : STOP_LOSS_PCT,
                "tp_pct"   : TAKE_PROFIT_PCT,
                "size_pct" : POSITION_SIZE,
                "raw_data" : {"price": price, "rsi": round(rsi,1), "vol_ratio": round(vol_ratio,2)},
            }
        except Exception as e:
            print(f"Scalper error {symbol}: {e}")
            return self._hold(f"Error: {e}")

    def _hold(self, reason: str) -> dict:
        return {"signal":"HOLD","score":0,"reasoning":reason,"sl_pct":STOP_LOSS_PCT,"tp_pct":TAKE_PROFIT_PCT,"size_pct":POSITION_SIZE,"raw_data":{}}
