import os, requests

GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_URL = "https://api.x.ai/v1/chat/completions"

def ask_grok(symbol, price, technical_signal, score):
    if not GROK_API_KEY:
        return {"vote": "HOLD", "confidence": "low", "reasoning": "No Grok key"}
    coin = symbol.replace("/USDT", "")
    prompt = f"""You are a crypto trading assistant with real-time X/Twitter access.
Coin: {coin} at ${price:,.2f}
Technical signal: {technical_signal} (score: {score:+d})
Check current X/Twitter sentiment for {coin} right now.
Respond EXACTLY:
VOTE: [BUY or SELL or HOLD]
CONFIDENCE: [high or medium or low]
REASONING: [1 sentence about current sentiment]"""
    try:
        r = requests.post(GROK_URL,
            headers={"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "grok-3-fast", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150},
            timeout=15)
        text = r.json()["choices"][0]["message"]["content"].strip()
        vote, confidence, reasoning = "HOLD", "low", ""
        for line in text.splitlines():
            if line.startswith("VOTE:"): vote = line.split(":",1)[1].strip().upper()
            elif line.startswith("CONFIDENCE:"): confidence = line.split(":",1)[1].strip().lower()
            elif line.startswith("REASONING:"): reasoning = line.split(":",1)[1].strip()
        if vote not in ("BUY","SELL","HOLD"): vote = "HOLD"
        return {"vote": vote, "confidence": confidence, "reasoning": reasoning}
    except Exception as e:
        print(f"Grok error: {e}")
        return {"vote": "HOLD", "confidence": "low", "reasoning": str(e)}
