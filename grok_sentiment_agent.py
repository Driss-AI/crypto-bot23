"""
GROK SENTIMENT AGENT
═══════════════════════════════════════════════════════════
Uses xAI's Grok model with real-time X/Twitter access.
This is the ONLY agent that can read live social media.

What Grok sees that others can't:
- Live X/Twitter posts about the coin
- Whale alert tweets
- Crypto influencer sentiment
- Breaking news before it hits mainstream
- Community mood in real time

Returns a sentiment signal the Orchestrator can use.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_URL     = "https://api.x.ai/v1/chat/completions"


class GrokSentimentAgent:
    def __init__(self):
        self.name  = "grok_sentiment"
        self.style = "sentiment"
        if not GROK_API_KEY:
            print("⚠️ GrokSentimentAgent: No GROK_API_KEY found")
        else:
            print("🤖 Grok Sentiment Agent initialized — X/Twitter access active")

    def analyze(self, symbol: str, price: float = 0, fear_greed: int = 50) -> dict:
        """
        Ask Grok to analyze real-time X/Twitter sentiment for the coin.
        Grok has live access to X — no other model can do this.
        """
        coin = symbol.replace("/USDT", "")
        print(f"  🤖 Grok analyzing {coin} sentiment on X/Twitter...")

        if not GROK_API_KEY:
            return self._empty(symbol, "No API key")

        prompt = f"""You are a crypto sentiment analyst with access to real-time X (Twitter) data.

Analyze the current X/Twitter sentiment for {coin} (${price:,.2f}) right now.

Look for:
1. Recent tweets from crypto influencers about {coin}
2. Whale alert mentions
3. Breaking news or FUD
4. Community mood — are people bullish or bearish?
5. Any unusual activity, hacks, partnerships, listings
6. Trending hashtags related to {coin}

Context:
- Fear & Greed Index: {fear_greed}/100
- Current price: ${price:,.2f}

Respond in EXACTLY this format:
SIGNAL: [BULLISH or BEARISH or NEUTRAL]
CONFIDENCE: [high or medium or low]
SCORE: [integer from -5 (very bearish) to +5 (very bullish)]
X_MOOD: [one word: euphoric/excited/hopeful/neutral/worried/fearful/panic]
KEY_INSIGHT: [1-2 sentences about the most important thing you found on X right now]
RISKS: [1 key risk from social sentiment]

Be specific about what you actually see on X right now. If you see whale movements, name them. If there's FUD, describe it."""

        try:
            response = requests.post(
                GROK_URL,
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type" : "application/json",
                },
                json={
                    "model"    : "grok-3",
                    "messages" : [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.3,
                },
                timeout=30,
            )

            if response.status_code != 200:
                print(f"  ⚠️ Grok API error: {response.status_code} — {response.text[:100]}")
                return self._empty(symbol, f"API error {response.status_code}")

            text = response.json()["choices"][0]["message"]["content"]
            return self._parse(symbol, text)

        except Exception as e:
            print(f"  ⚠️ Grok error: {e}")
            return self._empty(symbol, str(e))

    def _parse(self, symbol: str, text: str) -> dict:
        signal      = "NEUTRAL"
        confidence  = "low"
        score       = 0
        x_mood      = "neutral"
        key_insight = ""
        risks       = ""

        for line in text.strip().splitlines():
            line = line.strip()
            if line.startswith("SIGNAL:"):
                raw = line.split(":", 1)[1].strip().upper()
                if raw in ["BULLISH", "BEARISH", "NEUTRAL"]:
                    signal = raw
            elif line.startswith("CONFIDENCE:"):
                confidence = line.split(":", 1)[1].strip().lower()
            elif line.startswith("SCORE:"):
                try:
                    score = int(line.split(":", 1)[1].strip())
                    score = max(-5, min(5, score))
                except:
                    pass
            elif line.startswith("X_MOOD:"):
                x_mood = line.split(":", 1)[1].strip().lower()
            elif line.startswith("KEY_INSIGHT:"):
                key_insight = line.split(":", 1)[1].strip()
            elif line.startswith("RISKS:"):
                risks = line.split(":", 1)[1].strip()

        # Convert to standard signal format
        if signal == "BULLISH":
            action = "BUY"
        elif signal == "BEARISH":
            action = "SELL"
        else:
            action = "HOLD"

        print(f"    → {action} ({confidence}) | X mood: {x_mood} | score: {score:+d}")
        print(f"    💡 {key_insight[:80]}...")

        return {
            "agent"      : self.name,
            "style"      : self.style,
            "signal"     : action,
            "confidence" : confidence,
            "score"      : score,
            "x_mood"     : x_mood,
            "key_insight": key_insight,
            "risks"      : risks,
            "reasoning"  : f"X mood: {x_mood} | {key_insight}",
            "raw_text"   : text,
        }

    def _empty(self, symbol: str, reason: str) -> dict:
        return {
            "agent"      : self.name,
            "style"      : self.style,
            "signal"     : "HOLD",
            "confidence" : "low",
            "score"      : 0,
            "x_mood"     : "neutral",
            "key_insight": f"Grok unavailable: {reason}",
            "risks"      : "No sentiment data",
            "reasoning"  : f"Grok unavailable: {reason}",
        }


# ── Standalone test ───────────────────────────────────────
if __name__ == "__main__":
    agent = GrokSentimentAgent()
    result = agent.analyze("BTC/USDT", price=83000, fear_greed=21)
    print(f"\n{'='*50}")
    print(f"Signal:    {result['signal']} ({result['confidence']})")
    print(f"Score:     {result['score']:+d}")
    print(f"X Mood:    {result['x_mood']}")
    print(f"Insight:   {result['key_insight']}")
    print(f"Risks:     {result['risks']}")
