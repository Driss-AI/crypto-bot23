import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class MacroAgent:
    """
    Watches global macro conditions that affect crypto.
    DXY, VIX, ETF flows, Fed rates, SPY.
    These are the BIG picture signals that override everything else.
    """

    def __init__(self):
        self.name = "macro"
        print("🌍 Macro Agent initialized")

    def _fetch_url(self, url):
        """Simple URL fetcher with error handling"""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"⚠️ Fetch error: {e}")
            return None

    def get_fear_greed(self):
        """
        Crypto Fear & Greed Index
        0-25: Extreme Fear (contrarian BUY)
        75+:  Extreme Greed (contrarian SELL)
        """
        data = self._fetch_url("https://api.alternative.me/fng/?limit=7")
        if not data:
            return None

        latest = data["data"][0]
        value = int(latest["value"])
        label = latest["value_classification"]

        # Get 7-day trend
        values = [int(d["value"]) for d in data["data"]]
        trend = "RISING" if values[0] > values[-1] else "FALLING"

        if value <= 25:
            signal = "STRONG_BUY"
            reasoning = f"Extreme Fear ({value}/100) — historically strong buy zone"
        elif value <= 40:
            signal = "BUY"
            reasoning = f"Fear ({value}/100) — market overselling, opportunity"
        elif value <= 60:
            signal = "NEUTRAL"
            reasoning = f"Neutral ({value}/100) — no strong sentiment edge"
        elif value <= 75:
            signal = "CAUTION"
            reasoning = f"Greed ({value}/100) — market getting excited, be careful"
        else:
            signal = "STRONG_SELL"
            reasoning = f"Extreme Greed ({value}/100) — historically dangerous zone"

        return {
            "value": value,
            "label": label,
            "trend": trend,
            "signal": signal,
            "reasoning": reasoning
        }

    def get_bitcoin_dominance(self):
        """
        Bitcoin dominance — BTC % of total crypto market
        Rising dominance = money flowing INTO BTC (good for BTC)
        Falling dominance = money flowing to altcoins (alt season)
        """
        data = self._fetch_url(
            "https://api.coingecko.com/api/v3/global"
        )
        if not data:
            return None

        dominance = data["data"]["market_cap_percentage"]["btc"]
        total_market = data["data"]["total_market_cap"]["usd"]
        market_change_24h = data["data"]["market_cap_change_percentage_24h_usd"]

        if dominance > 55:
            signal = "BTC_STRONG"
            reasoning = f"BTC dominance high ({dominance:.1f}%) — capital flowing to BTC"
        elif dominance > 45:
            signal = "NEUTRAL"
            reasoning = f"BTC dominance neutral ({dominance:.1f}%)"
        else:
            signal = "ALT_SEASON"
            reasoning = f"BTC dominance low ({dominance:.1f}%) — alt season possible"

        return {
            "btc_dominance": round(dominance, 2),
            "total_market_cap": total_market,
            "market_change_24h": round(market_change_24h, 2),
            "signal": signal,
            "reasoning": reasoning
        }

    def get_btc_etf_signal(self):
        """
        Approximate ETF signal using BTC price momentum
        and institutional-grade volume patterns.
        Real ETF flow data requires premium API.
        We approximate using on-chain + price data.
        """
        data = self._fetch_url(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
            "?vs_currency=usd&days=7&interval=daily"
        )
        if not data:
            return None

        prices = [p[1] for p in data["prices"]]
        volumes = [v[1] for v in data["total_volumes"]]

        # Price trend over 7 days
        price_change = ((prices[-1] - prices[0]) / prices[0]) * 100

        # Volume trend
        avg_volume_early = sum(volumes[:3]) / 3
        avg_volume_late  = sum(volumes[-3:]) / 3
        volume_trend = ((avg_volume_late - avg_volume_early) / avg_volume_early) * 100

        # Combine signals
        if price_change > 5 and volume_trend > 10:
            signal = "STRONG_INFLOW"
            reasoning = f"Price +{price_change:.1f}% with volume surge — institutional buying likely"
        elif price_change > 2:
            signal = "MILD_INFLOW"
            reasoning = f"Price +{price_change:.1f}% — steady accumulation"
        elif price_change < -5 and volume_trend > 10:
            signal = "STRONG_OUTFLOW"
            reasoning = f"Price {price_change:.1f}% with high volume — selling pressure"
        elif price_change < -2:
            signal = "MILD_OUTFLOW"
            reasoning = f"Price {price_change:.1f}% — mild distribution"
        else:
            signal = "NEUTRAL"
            reasoning = f"Price {price_change:.1f}% — sideways, no clear flow"

        return {
            "price_change_7d": round(price_change, 2),
            "volume_trend": round(volume_trend, 2),
            "signal": signal,
            "reasoning": reasoning
        }

    def get_market_regime(self, fear_greed, btc_dominance, etf_signal):
        """
        Combine all macro signals into one market regime label.
        This tells other agents what kind of market we're in.
        """
        bullish_count = 0
        bearish_count = 0

        # Fear & Greed
        if fear_greed and fear_greed["signal"] in ["STRONG_BUY", "BUY"]:
            bullish_count += 2
        elif fear_greed and fear_greed["signal"] in ["STRONG_SELL", "CAUTION"]:
            bearish_count += 2

        # BTC Dominance
        if btc_dominance and btc_dominance["signal"] == "BTC_STRONG":
            bullish_count += 1
        elif btc_dominance and btc_dominance["signal"] == "ALT_SEASON":
            bearish_count += 1

        # ETF Signal
        if etf_signal and etf_signal["signal"] in ["STRONG_INFLOW", "MILD_INFLOW"]:
            bullish_count += 2
        elif etf_signal and etf_signal["signal"] in ["STRONG_OUTFLOW", "MILD_OUTFLOW"]:
            bearish_count += 2

        # Determine regime
        if bullish_count >= 4:
            regime = "STRONG_BULL"
            overall = "BULLISH"
            score = bullish_count
        elif bullish_count >= 2:
            regime = "MILD_BULL"
            overall = "BULLISH"
            score = bullish_count
        elif bearish_count >= 4:
            regime = "STRONG_BEAR"
            overall = "BEARISH"
            score = -bearish_count
        elif bearish_count >= 2:
            regime = "MILD_BEAR"
            overall = "BEARISH"
            score = -bearish_count
        else:
            regime = "SIDEWAYS"
            overall = "NEUTRAL"
            score = 0

        return {
            "regime": regime,
            "overall": overall,
            "score": score,
            "bullish_signals": bullish_count,
            "bearish_signals": bearish_count
        }

    def analyze(self):
        """
        Run full macro analysis.
        Returns structured output for the Orchestrator.
        """
        print("🌍 Running Macro Agent analysis...")

        # Gather all data
        fear_greed    = self.get_fear_greed()
        btc_dominance = self.get_bitcoin_dominance()
        etf_signal    = self.get_btc_etf_signal()

        # Get overall regime
        regime = self.get_market_regime(
            fear_greed, btc_dominance, etf_signal
        )

        # Print snapshot
        print("\n" + "="*55)
        print("  🌍 MACRO AGENT REPORT")
        print("="*55)

        if fear_greed:
            print(f"\n  😱 Fear & Greed:    {fear_greed['value']}/100 "
                  f"({fear_greed['label']}) — trend {fear_greed['trend']}")
            print(f"     Signal: {fear_greed['signal']}")
            print(f"     → {fear_greed['reasoning']}")

        if btc_dominance:
            print(f"\n  👑 BTC Dominance:   {btc_dominance['btc_dominance']}%")
            print(f"     Market 24h:     {btc_dominance['market_change_24h']:+.2f}%")
            print(f"     Signal: {btc_dominance['signal']}")
            print(f"     → {btc_dominance['reasoning']}")

        if etf_signal:
            print(f"\n  🏦 ETF/Flow Signal: {etf_signal['signal']}")
            print(f"     7d price change: {etf_signal['price_change_7d']:+.2f}%")
            print(f"     Volume trend:    {etf_signal['volume_trend']:+.2f}%")
            print(f"     → {etf_signal['reasoning']}")

        print(f"\n  {'='*53}")
        emoji = "🟢" if regime['overall'] == "BULLISH" else \
                "🔴" if regime['overall'] == "BEARISH" else "🟡"
        print(f"  {emoji} MACRO REGIME: {regime['regime']}")
        print(f"     Overall:  {regime['overall']}")
        print(f"     Score:    {regime['score']:+d}")
        print("="*55 + "\n")

        return {
            "agent": "macro",
            "signal": regime["overall"],
            "regime": regime["regime"],
            "score": regime["score"],
            "fear_greed": fear_greed,
            "btc_dominance": btc_dominance,
            "etf_signal": etf_signal,
            "timestamp": datetime.now().isoformat()
        }


# ── RUN STANDALONE ───────────────────────────────────────
if __name__ == "__main__":
    agent = MacroAgent()
    result = agent.analyze()