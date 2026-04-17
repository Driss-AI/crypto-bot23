"""
ENHANCED NEWS SCRAPER v4
========================
Free sources - no API keys needed:

1. CoinDesk RSS          - professional crypto news
2. CoinTelegraph RSS     - breaking news  
3. Decrypt RSS           - crypto/web3
4. Bitcoin Magazine RSS  - Bitcoin focused
5. The Block RSS         - institutional
6. Blockworks RSS        - crypto finance
7. Fear & Greed Index    - market mood
8. CoinGecko Trending    - what's hot
9. Reddit r/CryptoCurrency - community mood
10. ForexFactory Calendar - macro events (NEW)
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


#  RSS FEEDS 

RSS_FEEDS = [
    ("CoinDesk",         "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph",    "https://cointelegraph.com/rss"),
    ("Decrypt",          "https://decrypt.co/feed"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("The Block",        "https://www.theblock.co/rss.xml"),
    ("Blockworks",       "https://blockworks.co/feed"),
]

BULLISH_WORDS = ["surge","rally","bull","soar","gain","rise","adopt","approve","record","high","pump","moon","etf","institutional"]
BEARISH_WORDS = ["crash","drop","ban","hack","fraud","sell","bear","fall","plunge","fear","dump","liquidat","sec","lawsuit","restrict"]


def fetch_rss(url: str, source: str, limit: int = 5) -> list:
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBot/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            root = ET.fromstring(r.read())
        ch = root.find("channel") or root
        for item in list(ch.findall("item"))[:limit]:
            title = item.findtext("title", "").strip()
            if title:
                items.append({"source": source, "title": title,
                               "desc": item.findtext("description","")[:150].strip()})
    except Exception as e:
        print(f"  {source} RSS error: {e}")
    return items


def get_fear_greed() -> dict:
    try:
        req = urllib.request.Request(
            "https://api.alternative.me/fng/?limit=3",
            headers={"User-Agent": "DrissBot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        d = data["data"]
        current = int(d[0]["value"])
        prev    = int(d[1]["value"]) if len(d) > 1 else current
        trend   = " improving" if current > prev else " worsening" if current < prev else " stable"
        return {"value": current, "label": d[0]["value_classification"], "trend": trend}
    except Exception as e:
        print(f"  Fear&Greed error: {e}")
        return {"value": 50, "label": "Neutral", "trend": " stable"}


def get_coingecko_trending() -> list:
    try:
        req = urllib.request.Request(
            "https://api.coingecko.com/api/v3/search/trending",
            headers={"User-Agent": "DrissBot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        return [c["item"]["name"] for c in data.get("coins", [])[:5]]
    except Exception as e:
        print(f"  CoinGecko error: {e}")
        return []


def get_forex_factory_events() -> str:
    """Get today's high-impact macro events from ForexFactory."""
    try:
        req = urllib.request.Request(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            headers={"User-Agent": "DrissBot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            events = json.loads(r.read())

        now    = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=8)
        relevant_currencies = {"USD", "EUR", "GBP", "JPY", "CNY", "All"}
        high_events = []

        for ev in events:
            if ev.get("impact") != "High": continue
            if ev.get("country") not in relevant_currencies: continue
            try:
                dt = datetime.fromisoformat(ev["date"].replace("Z","+00:00")).astimezone(timezone.utc)
                if now - timedelta(hours=1) <= dt <= cutoff:
                    diff = int((dt - now).total_seconds() / 60)
                    status = f"in {diff}min" if diff > 0 else f"{abs(diff)}min ago"
                    high_events.append(f"{ev['title']} ({ev['country']})  {status} | forecast:{ev.get('forecast','?')} prev:{ev.get('previous','?')}")
            except: pass

        if high_events:
            return " HIGH-IMPACT EVENTS SOON:\n" + "\n".join(high_events[:4])
        return "No high-impact events next 8 hours "
    except Exception as e:
        return f"Calendar unavailable: {e}"


def score_headlines(headlines: list) -> dict:
    bull = 0
    bear = 0
    for h in headlines:
        text = h["title"].lower()
        bull += sum(1 for w in BULLISH_WORDS if w in text)
        bear += sum(1 for w in BEARISH_WORDS if w in text)
    total = bull + bear
    if total == 0:
        sentiment = "NEUTRAL"
        score = 0
    else:
        score = int((bull - bear) / total * 10)
        if score >= 3:   sentiment = "BULLISH"
        elif score >= 1: sentiment = "SLIGHTLY BULLISH"
        elif score <= -3:sentiment = "BEARISH"
        elif score <= -1:sentiment = "SLIGHTLY BEARISH"
        else:            sentiment = "NEUTRAL"
    return {"sentiment": sentiment, "score": score, "bullish_signals": bull, "bearish_signals": bear}


def get_full_sentiment() -> dict:
    headlines = []
    for source, url in RSS_FEEDS:
        headlines.extend(fetch_rss(url, source))

    fg          = get_fear_greed()
    trending    = get_coingecko_trending()
    macro       = get_forex_factory_events()
    news_scores = score_headlines(headlines)

    return {
        "headlines"   : headlines[:20],
        "fear_greed"  : fg,
        "trending"    : trending,
        "macro_events": macro,
        "news_scores" : news_scores,
    }


def format_for_ai(data: dict) -> str:
    fg     = data.get("fear_greed", {})
    scores = data.get("news_scores", {})
    macro  = data.get("macro_events", "")

    lines = [
        f"MARKET MOOD: Fear & Greed = {fg.get('value',50)}/100 ({fg.get('label','?')}) {fg.get('trend','')}",
        f"NEWS SENTIMENT: {scores.get('sentiment','?')} (score:{scores.get('score',0):+d} | bull:{scores.get('bullish_signals',0)} bear:{scores.get('bearish_signals',0)})",
        "",
        f"MACRO CALENDAR: {macro}",
        "",
        "TOP HEADLINES:",
    ]

    for h in data.get("headlines", [])[:8]:
        lines.append(f"  [{h['source']}] {h['title']}")

    trending = data.get("trending", [])
    if trending:
        lines.append(f"\nTRENDING COINS: {', '.join(trending)}")

    return "\n".join(lines)
