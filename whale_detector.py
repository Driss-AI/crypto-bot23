"""
WHALE DETECTOR
═══════════════════════════════════════════════════════════
Tracks large crypto movements using free sources:

1. Etherscan API     — ETH large transactions (free key)
2. Blockchain.com    — BTC large transactions (no key needed)
3. CoinGecko         — Top holder concentrations
4. Mempool.space     — BTC mempool large txs (no key needed)

What we're looking for:
- Large BTC/ETH moving TO exchanges = sell pressure
- Large BTC/ETH moving FROM exchanges = accumulation
- Whale wallet accumulation patterns
- Exchange inflow/outflow trends
"""

import os
import json
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# Known exchange addresses for context
KNOWN_EXCHANGES = {
    # ETH exchanges
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
    "0xd551234ae421e3bcba99a0da6d736074f22192ff": "Binance",
    "0x564286362092d8e7936f0549571a803b203aaced": "Binance",
    "0xfe9e8709d3215310075d67e3ed32a380ccf451c8": "Binance",
    "0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67": "Binance",
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance",
    "0xa910f92acdaf488fa6ef02174fb86208ad7722ba": "Kraken",
    "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken",
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
    "0xab5c66752a9e8167967685f1450532fb96d5d24f": "Huobi",
    "0x6748f50f686bfbca6fe8ad62b22228b87f31ff2b": "Huobi",
    "0xfdb16996831753d5331ff813c29a93c76834a0ad": "Huobi",
}


# ── BTC WHALE DETECTOR (Blockchain.com) ──────────────────────────────────────

def get_btc_large_txs(min_btc: float = 100) -> list[dict]:
    """
    Uses Blockchain.com public API to find recent large BTC transactions.
    No API key needed.
    """
    whales = []
    try:
        # Get latest block
        url = "https://blockchain.info/latestblock"
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            latest = json.loads(r.read())

        block_hash = latest.get("hash", "")
        if not block_hash:
            return whales

        # Get transactions in latest block
        url = f"https://blockchain.info/rawblock/{block_hash}"
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            block = json.loads(r.read())

        txs = block.get("tx", [])
        for tx in txs:
            # Calculate total output value
            total_out = sum(o.get("value", 0) for o in tx.get("out", [])) / 1e8  # satoshi to BTC
            if total_out >= min_btc:
                tx_hash = tx.get("hash", "")[:16] + "..."
                whales.append({
                    "chain"    : "BTC",
                    "amount"   : round(total_out, 2),
                    "amount_usd": 0,  # will calculate with price
                    "tx_hash"  : tx_hash,
                    "type"     : "LARGE_TX",
                    "title"    : f"🐋 BTC: {total_out:.1f} BTC moved (${total_out * 74000:,.0f})",
                    "signal"   : "NEUTRAL",
                })

        print(f"  ✅ BTC Whales: {len(whales)} large txs (≥{min_btc} BTC)")

    except Exception as e:
        print(f"  ⚠️ BTC Whales error: {e}")

    return whales[:5]  # top 5


# ── ETH WHALE DETECTOR (Etherscan) ───────────────────────────────────────────

def get_eth_large_txs(min_eth: float = 500) -> list[dict]:
    """
    Uses Etherscan free API to find recent large ETH transactions.
    Identifies if they're going to/from exchanges.
    """
    whales = []

    if not ETHERSCAN_KEY:
        print("  ⚠️ ETH Whales: No ETHERSCAN_API_KEY set")
        return whales

    try:
        # Get latest ETH block transactions
        url = (
            f"https://api.etherscan.io/api"
            f"?module=proxy&action=eth_getBlockByNumber"
            f"&tag=latest&boolean=true"
            f"&apikey={ETHERSCAN_KEY}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        txs = data.get("result", {}).get("transactions", [])

        for tx in txs:
            # Convert hex value to ETH
            value_hex = tx.get("value", "0x0") if isinstance(tx, dict) else "0x0"
            try:
                value_wei = int(value_hex, 16)
                value_eth = value_wei / 1e18
            except:
                continue

            if value_eth >= min_eth:
                from_addr = tx.get("from", "").lower()
                to_addr   = tx.get("to",   "").lower()

                from_name = KNOWN_EXCHANGES.get(from_addr, from_addr[:8] + "...")
                to_name   = KNOWN_EXCHANGES.get(to_addr,   to_addr[:8]   + "...")

                # Determine signal
                if to_addr in KNOWN_EXCHANGES:
                    signal  = "BEARISH"  # moving TO exchange = potential sell
                    emoji   = "📤"
                    context = f"→ {to_name} (exchange inflow ⚠️)"
                elif from_addr in KNOWN_EXCHANGES:
                    signal  = "BULLISH"  # moving FROM exchange = accumulation
                    emoji   = "📥"
                    context = f"← {from_name} (exchange outflow ✅)"
                else:
                    signal  = "NEUTRAL"
                    emoji   = "🐋"
                    context = f"{from_name} → {to_name}"

                whales.append({
                    "chain"  : "ETH",
                    "amount" : round(value_eth, 2),
                    "from"   : from_name,
                    "to"     : to_name,
                    "signal" : signal,
                    "title"  : f"{emoji} ETH: {value_eth:.0f} ETH (${value_eth*2400:,.0f}) {context}",
                })

        print(f"  ✅ ETH Whales: {len(whales)} large txs (≥{min_eth} ETH)")

    except Exception as e:
        print(f"  ⚠️ ETH Whales error: {e}")

    return whales[:5]


# ── BTC MEMPOOL (large pending txs) ──────────────────────────────────────────

def get_btc_mempool_whales(min_btc: float = 50) -> dict:
    """
    Checks mempool.space for BTC network activity and large pending txs.
    No key needed.
    """
    result = {
        "tx_count"     : 0,
        "total_fee_btc": 0,
        "signal"       : "NEUTRAL",
        "title"        : "Mempool data unavailable",
    }
    try:
        req = urllib.request.Request(
            "https://mempool.space/api/mempool",
            headers={"User-Agent": "DrissBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())

        tx_count = data.get("count", 0)
        vsize    = data.get("vsize", 0)

        if tx_count > 100_000:
            signal = "HIGH_ACTIVITY"
            note   = "Extreme network activity — big move likely"
        elif tx_count > 50_000:
            signal = "ELEVATED"
            note   = "Elevated activity — market is busy"
        elif tx_count > 10_000:
            signal = "NORMAL"
            note   = "Normal activity"
        else:
            signal = "QUIET"
            note   = "Low activity — quiet market"

        result = {
            "tx_count"     : tx_count,
            "vsize_mb"     : round(vsize / 1_000_000, 2),
            "signal"       : signal,
            "title"        : f"⛓️ BTC Mempool: {tx_count:,} txs — {note}",
        }
        print(f"  ✅ BTC Mempool: {tx_count:,} pending txs ({signal})")

    except Exception as e:
        print(f"  ⚠️ BTC Mempool: {e}")

    return result


# ── COINGECKO EXCHANGE FLOWS ──────────────────────────────────────────────────

def get_exchange_flows(coin_id: str = "bitcoin") -> dict:
    """
    Uses CoinGecko to approximate exchange flows from price + volume data.
    """
    result = {"signal": "NEUTRAL", "reasoning": "No data"}
    try:
        url = (
            f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            f"?localization=false&tickers=false&community_data=false"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        market = data.get("market_data", {})
        price_change_24h = market.get("price_change_percentage_24h", 0) or 0
        price_change_7d  = market.get("price_change_percentage_7d",  0) or 0
        volume_24h       = market.get("total_volume",  {}).get("usd", 0) or 0
        market_cap       = market.get("market_cap",    {}).get("usd", 1) or 1
        vol_ratio        = volume_24h / market_cap

        if price_change_24h > 5 and vol_ratio > 0.05:
            signal    = "STRONG_INFLOW"
            reasoning = f"Price +{price_change_24h:.1f}% with high volume — strong buying"
        elif price_change_24h > 2:
            signal    = "MILD_INFLOW"
            reasoning = f"Price +{price_change_24h:.1f}% — accumulation"
        elif price_change_24h < -5 and vol_ratio > 0.05:
            signal    = "STRONG_OUTFLOW"
            reasoning = f"Price {price_change_24h:.1f}% with high volume — selling pressure"
        elif price_change_24h < -2:
            signal    = "MILD_OUTFLOW"
            reasoning = f"Price {price_change_24h:.1f}% — distribution"
        else:
            signal    = "NEUTRAL"
            reasoning = f"Price {price_change_24h:.1f}% — sideways"

        result = {
            "signal"       : signal,
            "price_24h"    : round(price_change_24h, 2),
            "price_7d"     : round(price_change_7d, 2),
            "vol_ratio"    : round(vol_ratio, 4),
            "reasoning"    : reasoning,
        }
        print(f"  ✅ {coin_id} flows: {signal}")

    except Exception as e:
        print(f"  ⚠️ Exchange flows error: {e}")

    return result


# ── MAIN WHALE ANALYZER ───────────────────────────────────────────────────────

def analyze_whales(symbol: str = "BTC/USDT") -> dict:
    """
    Full whale analysis for a given coin.
    Returns structured signal for the Orchestrator.
    """
    coin = symbol.replace("/USDT", "").upper()
    print(f"\n🐋 Whale Detector analyzing {coin}...")

    # Map to CoinGecko IDs
    cg_ids = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
    }
    cg_id = cg_ids.get(coin, coin.lower())

    # Gather data
    btc_whales = get_btc_large_txs(100)  if coin == "BTC" else []
    eth_whales = get_eth_large_txs(500)  if coin == "ETH" else []
    mempool    = get_btc_mempool_whales() if coin == "BTC" else {}
    flows      = get_exchange_flows(cg_id)

    # Score
    score   = 0
    reasons = []

    # Exchange flows
    flow_sig = flows.get("signal", "NEUTRAL")
    if flow_sig == "STRONG_INFLOW":
        score += 3
    elif flow_sig == "MILD_INFLOW":
        score += 1
    elif flow_sig == "STRONG_OUTFLOW":
        score -= 3
    elif flow_sig == "MILD_OUTFLOW":
        score -= 1
    reasons.append(flows.get("reasoning", ""))

    # ETH whale signals
    bearish_eth = sum(1 for w in eth_whales if w["signal"] == "BEARISH")
    bullish_eth = sum(1 for w in eth_whales if w["signal"] == "BULLISH")
    if bearish_eth > bullish_eth:
        score -= 2
        reasons.append(f"{bearish_eth} large ETH txs to exchanges ⚠️")
    elif bullish_eth > bearish_eth:
        score += 2
        reasons.append(f"{bullish_eth} large ETH txs from exchanges ✅")

    # Mempool signal
    if mempool.get("signal") == "HIGH_ACTIVITY":
        score += 1
        reasons.append("High BTC mempool activity")
    elif mempool.get("signal") == "QUIET":
        score -= 1
        reasons.append("Very quiet BTC mempool")

    # Convert to signal
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

    # Build whale alerts list
    all_alerts = (
        [w["title"] for w in btc_whales[:3]] +
        [w["title"] for w in eth_whales[:3]] +
        ([mempool["title"]] if mempool.get("title") else [])
    )

    result = {
        "agent"      : "whale_detector",
        "symbol"     : symbol,
        "signal"     : signal,
        "confidence" : confidence,
        "score"      : score,
        "reasoning"  : " | ".join(r for r in reasons if r),
        "alerts"     : all_alerts,
        "flows"      : flows,
        "mempool"    : mempool,
    }

    print(f"  → {signal} ({confidence}) | score: {score:+d}")
    return result


def format_whale_summary(result: dict) -> str:
    """Format whale analysis for AI prompt injection."""
    lines = [
        f"🐋 WHALE ANALYSIS: {result['signal']} ({result['confidence']})",
        f"Score: {result['score']:+d}",
        f"Reasoning: {result['reasoning']}",
    ]
    if result.get("alerts"):
        lines.append("Alerts:")
        for a in result["alerts"]:
            lines.append(f"  • {a}")
    return "\n".join(lines)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🐋 WHALE DETECTOR TEST")
    print("="*55)

    for symbol in ["BTC/USDT", "ETH/USDT"]:
        result = analyze_whales(symbol)
        print(f"\n{'='*55}")
        print(f"  {symbol}: {result['signal']} ({result['confidence']})")
        print(f"  Score: {result['score']:+d}")
        print(f"  Why: {result['reasoning']}")
        if result["alerts"]:
            print(f"  Alerts:")
            for a in result["alerts"]:
                print(f"    • {a}")
        print("="*55)
