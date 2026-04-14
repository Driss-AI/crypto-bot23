"""
ENHANCED NEWS SCRAPER v3 — 100% Free Sources
All free, no API keys, no accounts needed.

Sources:
1. CoinDesk RSS
2. CoinTelegraph RSS
3. Decrypt RSS
4. Bitcoin Magazine RSS
5. The Block RSS
6. Blockworks RSS
7. Fear & Greed Index
8. Whale Alert (optional free key)
9. CoinGecko Trending
10. Reddit
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import os

RSS_FEEDS = [
    ("CoinDesk",         "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph",    "https://cointelegraph.com/rss"),
    ("Decrypt",          "https://decrypt.co/feed"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("The Block",        "https://www.theblock.co/rss.xml"),
    ("Blockworks",       "https://blockworks.co/feed"),
]

BULLISH_WORDS = ["surge","rally","bull","breakout","adoption","buy","gain","rise","pump","ath","record","green","up","bullish","moon","inflow","accumulation","etf","approved","launch","partnership","growth","profit","recovery","rebound","strong","positive"]
BEARISH_WORDS = ["crash","bear","dump","fear","ban","hack","sell","drop","fall","red","warning","risk","collapse","down","bearish","outflow","liquidation","lawsuit","regulation","crackdown","loss","weak","negative","correction","decline","panic"]


def fetch_rss(url, source_name, limit=5):
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read()
        root    = ET.fromstring(content)
        channel = root.find("channel") or root
        for item in list(channel.findall("item"))[:limit]:
            title = item.findtext("title", "").strip()
            if title:
                items.append({"source": source_name, "title": title})
        print(f"  ✅ {source_name}: {len(items)} articles")
    except Exception as e:
        print(f"  ⚠️ {source_name}: {e}")
    return items


def get_fear_greed():
    try:
        req = urllib.request.Request("https://api.alternative.me/fng/?limit=7", headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        latest  = data["data"][0]
        value   = int(latest["value"])
        label   = latest["value_classification"]
        history = [int(d["value"]) for d in data["data"]]
        trend   = "RISING" if history[0] > history[-1] else "FALLING"
        print(f"  ✅ Fear & Greed: {value}/100 ({label}) {trend}")
        return {"value": value, "label": label, "trend": trend, "change_7d": history[0]-history[-1]}
    except Exception as e:
        print(f"  ⚠️ Fear & Greed: {e}")
        return {"value": 50, "label": "Neutral", "trend": "FLAT", "change_7d": 0}


def get_whale_alerts():
    api_key = os.getenv("WHALE_ALERT_KEY", "")
    if not api_key:
        return []
    alerts = []
    try:
        url = f"https://api.whale-alert.io/v1/transactions?api_key={api_key}&min_value=1000000&limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        for tx in data.get("transactions", []):
            symbol = tx.get("symbol","").upper()
            amt    = tx.get("amount_usd", 0)
            frm    = tx.get("from",{}).get("owner","unknown")
            to     = tx.get("to",{}).get("owner","unknown")
            alerts.append({"symbol":symbol,"amount_usd":amt,"title":f"🐋 ${amt/1e6:.1f}M {symbol}: {frm} → {to}"})
        print(f"  ✅ Whale Alert: {len(alerts)} txs")
    except Exception as e:
        print(f"  ⚠️ Whale Alert: {e}")
    return alerts


def get_trending():
    items = []
    try:
        req = urllib.request.Request("https://api.coingecko.com/api/v3/search/trending", headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for c in data.get("coins",[])[:5]:
            item = c.get("item",{})
            items.append({"name":item.get("name",""),"symbol":item.get("symbol","").upper(),"title":f"🔥 Trending: {item.get('name','')} ({item.get('symbol','').upper()})"})
        print(f"  ✅ Trending: {len(items)} coins")
    except Exception as e:
        print(f"  ⚠️ Trending: {e}")
    return items


def get_reddit(subreddit, limit=5):
    items = []
    try:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for post in data["data"]["children"]:
            d = post["data"]
            items.append({"source":f"r/{subreddit}","title":d["title"],"score":d["score"]})
        print(f"  ✅ r/{subreddit}: {len(items)} posts")
    except Exception as e:
        print(f"  ⚠️ r/{subreddit}: {e}")
    return items


def score_headlines(headlines):
    bull = sum(1 for h in headlines for w in BULLISH_WORDS if w in h.lower())
    bear = sum(1 for h in headlines for w in BEARISH_WORDS if w in h.lower())
    total = bull + bear
    return round((bull-bear)/total if total > 0 else 0, 3), bull, bear


def get_full_sentiment(coins=None):
    if coins is None:
        coins = ["BTC","ETH","SOL","BNB"]

    print("\n📰 Fetching full market sentiment...")

    fear_greed = get_fear_greed()
    trending   = get_trending()
    whales     = get_whale_alerts()
    reddit_btc = get_reddit("Bitcoin", 5)
    reddit_cc  = get_reddit("CryptoCurrency", 5)

    all_rss = []
    for source_name, url in RSS_FEEDS:
        all_rss.extend(fetch_rss(url, source_name, 4))

    headlines = []
    for item in all_rss:
        headlines.append(f"[{item['source']}] {item['title']}")
    for item in reddit_btc + reddit_cc:
        headlines.append(f"[{item['source']} ⬆{item.get('score',0)}] {item['title']}")
    for item in whales:
        headlines.append(f"[WHALE] {item['title']}")
    for item in trending:
        headlines.append(f"[TRENDING] {item['title']}")

    score, bull, bear = score_headlines(headlines)

    print(f"\n  📊 Sentiment: {score:+.3f} (🟢{bull} bull / 🔴{bear} bear)")
    print(f"  📰 {len(headlines)} total signals")

    return {
        "timestamp"      : datetime.now().isoformat(),
        "fear_greed"     : fear_greed,
        "headlines"      : headlines[:25],
        "whale_alerts"   : whales,
        "trending"       : trending,
        "sentiment_score": score,
        "bull_count"     : bull,
        "bear_count"     : bear,
    }


def format_for_ai(sentiment, coin="BTC"):
    fg = sentiment["fear_greed"]
    lines = [
        f"📰 SENTIMENT — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"😱 Fear & Greed: {fg['value']}/100 ({fg['label']}) | Trend: {fg['trend']} | 7d: {fg['change_7d']:+d}",
        f"📊 Score: {sentiment['sentiment_score']:+.3f} (🟢{sentiment['bull_count']} / 🔴{sentiment['bear_count']})",
        f"",
    ]
    if sentiment["whale_alerts"]:
        lines.append("🐋 WHALE MOVEMENTS:")
        for w in sentiment["whale_alerts"]:
            lines.append(f"  • {w['title']}")
        lines.append("")
    if sentiment["trending"]:
        lines.append("🔥 TRENDING:")
        for t in sentiment["trending"][:3]:
            lines.append(f"  • {t['title']}")
        lines.append("")
    lines.append("🗞️ TOP HEADLINES:")
    for h in sentiment["headlines"][:15]:
        lines.append(f"  • {h}")
    return "\n".join(lines)


# Legacy compatibility
def get_latest_news():
    sentiment = get_full_sentiment()
    return format_for_ai(sentiment)


if __name__ == "__main__":
    sentiment = get_full_sentiment()
    print("\n" + "="*60)
    print(format_for_ai(sentiment))
    print("="*60)
