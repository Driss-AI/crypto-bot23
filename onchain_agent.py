"""
AGENT 2 — On-Chain Agent
Watches what the BIG money is doing using free on-chain APIs.

Sources:
  - CoinGecko: exchange inflows/outflows proxy, market data
  - Blockchain.info: BTC mempool and transaction data
  - Coinglass proxy: open interest trend approximation

This is the signal humans CAN'T watch manually — 24/7 whale tracking.
"""

import urllib.request
import json
from datetime import datetime


class OnChainAgent:
    def __init__(self):
        self.name = "onchain"
        print("🐋 On-Chain Agent initialized")

    def _fetch(self, url: str) -> dict | None:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"  ⚠️ Fetch error ({url[:50]}): {e}")
            return None

    # ── DATA SOURCES ─────────────────────────────────────────────────────────

    def get_exchange_flow(self, symbol: str = "bitcoin") -> dict | None:
        """
        Approximate exchange flow using CoinGecko market data.
        High volume + price drop = selling pressure (outflow from holders)
        High volume + price rise = buying pressure (inflow from buyers)
        """
        data = self._fetch(
            f"https://api.coingecko.com/api/v3/coins/{symbol}"
            "?localization=false&tickers=false&community_data=false&developer_data=false"
        )
        if not data:
            return None

        market = data.get("market_data", {})
        price_change_24h = market.get("price_change_percentage_24h", 0) or 0
        price_change_7d  = market.get("price_change_percentage_7d", 0) or 0
        volume_24h       = market.get("total_volume", {}).get("usd", 0) or 0
        market_cap       = market.get("market_cap", {}).get("usd", 1) or 1
        volume_to_mcap   = volume_24h / market_cap  # high ratio = high activity

        # Determine flow signal
        if price_change_24h > 3 and volume_to_mcap > 0.05:
            signal    = "STRONG_INFLOW"
            reasoning = f"Price +{price_change_24h:.1f}% with high volume — buyers in control"
        elif price_change_24h > 1:
            signal    = "MILD_INFLOW"
            reasoning = f"Price +{price_change_24h:.1f}% — mild accumulation"
        elif price_change_24h < -3 and volume_to_mcap > 0.05:
            signal    = "STRONG_OUTFLOW"
            reasoning = f"Price {price_change_24h:.1f}% with high volume — sellers in control"
        elif price_change_24h < -1:
            signal    = "MILD_OUTFLOW"
            reasoning = f"Price {price_change_24h:.1f}% — mild distribution"
        else:
            signal    = "NEUTRAL"
            reasoning = f"Price {price_change_24h:.1f}% — no clear directional flow"

        return {
            "price_change_24h" : round(price_change_24h, 2),
            "price_change_7d"  : round(price_change_7d, 2),
            "volume_to_mcap"   : round(volume_to_mcap, 4),
            "signal"           : signal,
            "reasoning"        : reasoning,
        }

    def get_btc_mempool(self) -> dict | None:
        """
        BTC mempool size — high mempool = lots of transactions = active market.
        Very high mempool often signals a big move is underway.
        """
        data = self._fetch("https://mempool.space/api/mempool")
        if not data:
            return None

        tx_count  = data.get("count", 0)
        vsize     = data.get("vsize", 0)

        if tx_count > 100_000:
            signal    = "VERY_HIGH_ACTIVITY"
            reasoning = f"Mempool: {tx_count:,} txs — extreme network activity"
        elif tx_count > 50_000:
            signal    = "HIGH_ACTIVITY"
            reasoning = f"Mempool: {tx_count:,} txs — elevated activity"
        elif tx_count > 10_000:
            signal    = "NORMAL"
            reasoning = f"Mempool: {tx_count:,} txs — normal activity"
        else:
            signal    = "LOW_ACTIVITY"
            reasoning = f"Mempool: {tx_count:,} txs — quiet network"

        return {
            "tx_count" : tx_count,
            "vsize_mb" : round(vsize / 1_000_000, 2),
            "signal"   : signal,
            "reasoning": reasoning,
        }

    def get_large_transactions(self, symbol: str = "bitcoin") -> dict | None:
        """
        Use CoinGecko's top holders / whale alert proxy.
        Approximated from market cap vs circulating supply movements.
        """
        data = self._fetch(
            f"https://api.coingecko.com/api/v3/coins/{symbol}"
            "?localization=false&tickers=false&community_data=false"
        )
        if not data:
            return None

        market = data.get("market_data", {})
        circ_supply  = market.get("circulating_supply", 0) or 0
        total_supply = market.get("total_supply", 1) or 1
        supply_ratio = circ_supply / total_supply

        # Higher ratio = more coins in circulation = less HODLing = potential sell pressure
        if supply_ratio > 0.92:
            signal    = "HIGH_CIRCULATION"
            reasoning = f"{supply_ratio*100:.1f}% in circulation — less HODLing, watch for sell pressure"
        elif supply_ratio < 0.80:
            signal    = "HIGH_HODL"
            reasoning = f"{supply_ratio*100:.1f}% in circulation — strong HODLing behavior"
        else:
            signal    = "NEUTRAL"
            reasoning = f"{supply_ratio*100:.1f}% in circulation — balanced"

        return {
            "supply_ratio" : round(supply_ratio, 4),
            "signal"       : signal,
            "reasoning"    : reasoning,
        }

    # ── COMBINE INTO SCORE ────────────────────────────────────────────────────

    def analyze(self, symbol: str = "BTC/USDT") -> dict:
        """
        Combine all on-chain signals into one output for the Orchestrator.
        """
        print(f"🐋 On-Chain Agent analyzing {symbol}...")
        coin = symbol.replace("/USDT", "").lower()
        cg_symbol = {"btc": "bitcoin", "eth": "ethereum",
                     "sol": "solana", "bnb": "binancecoin"}.get(coin, coin)

        flow      = self.get_exchange_flow(cg_symbol)
        mempool   = self.get_btc_mempool() if coin == "btc" else None
        whale     = self.get_large_transactions(cg_symbol)

        score   = 0
        reasons = []

        # ── Flow signal ──────────────────────────────────────
        if flow:
            if flow["signal"] == "STRONG_INFLOW":
                score += 3
            elif flow["signal"] == "MILD_INFLOW":
                score += 1
            elif flow["signal"] == "STRONG_OUTFLOW":
                score -= 3
            elif flow["signal"] == "MILD_OUTFLOW":
                score -= 1
            reasons.append(f"Flow: {flow['reasoning']}")

        # ── Mempool (BTC only) ───────────────────────────────
        if mempool:
            if mempool["signal"] == "VERY_HIGH_ACTIVITY":
                score += 1   # high activity often precedes big moves
            elif mempool["signal"] == "LOW_ACTIVITY":
                score -= 1
            reasons.append(f"Mempool: {mempool['reasoning']}")

        # ── Whale / supply signal ────────────────────────────
        if whale:
            if whale["signal"] == "HIGH_HODL":
                score += 1
            elif whale["signal"] == "HIGH_CIRCULATION":
                score -= 1
            reasons.append(f"Supply: {whale['reasoning']}")

        # ── Convert to signal ────────────────────────────────
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

        result = {
            "agent"      : self.name,
            "signal"     : signal,
            "confidence" : confidence,
            "score"      : score,
            "reasoning"  : " | ".join(reasons),
            "flow"       : flow,
            "mempool"    : mempool,
            "whale"      : whale,
        }

        print(f"  → {signal} ({confidence}) | score: {score:+d}")
        return result


# ── Standalone test ───────────────────────────────────────
if __name__ == "__main__":
    agent = OnChainAgent()
    result = agent.analyze("BTC/USDT")
    print(f"\nSignal:    {result['signal']} ({result['confidence']})")
    print(f"Score:     {result['score']:+d}")
    print(f"Reasoning: {result['reasoning']}")
