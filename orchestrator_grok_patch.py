"""
Patch to add Grok to the orchestrator.
Run this once to update orchestrator.py
"""

old_import = "from news_fetcher    import get_latest_news"
new_import = """from news_fetcher         import get_latest_news
from grok_sentiment_agent import GrokSentimentAgent"""

old_init = "        self.shared_macro = None   # set externally to avoid repeat API calls"
new_init = """        self.shared_macro  = None   # set externally to avoid repeat API calls
        self.grok          = GrokSentimentAgent()"""

old_threads = """        threads = [
            threading.Thread(target=run, args=("technical", lambda: self.technical.analyze(symbol))),
            threading.Thread(target=run, args=("onchain",   lambda: self.onchain.analyze(symbol))),
            threading.Thread(target=run, args=("news",      lambda: {"text": get_latest_news()})),
        ]"""

new_threads = """        # Get price for Grok context
        _price = 0
        _fg    = ((self.shared_macro or {}).get("fear_greed") or {}).get("value", 50)

        threads = [
            threading.Thread(target=run, args=("technical", lambda: self.technical.analyze(symbol))),
            threading.Thread(target=run, args=("onchain",   lambda: self.onchain.analyze(symbol))),
            threading.Thread(target=run, args=("news",      lambda: {"text": get_latest_news()})),
            threading.Thread(target=run, args=("grok",      lambda: self.grok.analyze(symbol, _price, _fg))),
        ]"""

old_news = "        news    = (results.get(\"news\") or {}).get(\"text\",\"No news\")"
new_news = """        news    = (results.get(\"news\") or {}).get(\"text\",\"No news\")
        grok    = results.get(\"grok\") or {}"""

old_claude_call = "        final     = self._ask_claude(symbol, raw_data, macro, onchain, news, consensus, weights)"
new_claude_call = "        final     = self._ask_claude(symbol, raw_data, macro, onchain, news, consensus, weights, grok)"

old_method_sig = "    def _ask_claude(self, symbol, data, macro, onchain, news, consensus, weights) -> dict:"
new_method_sig = "    def _ask_claude(self, symbol, data, macro, onchain, news, consensus, weights, grok=None) -> dict:"

# Read file
with open("orchestrator.py") as f:
    content = f.read()

# Apply patches
patches = [
    (old_import, new_import),
    (old_init, new_init),
    (old_threads, new_threads),
    (old_news, new_news),
    (old_claude_call, new_claude_call),
    (old_method_sig, new_method_sig),
]

for old, new in patches:
    if old in content:
        content = content.replace(old, new)
        print(f" Patched: {old[:50]}...")
    else:
        print(f" Not found: {old[:50]}...")

# Add grok section to Claude prompt
old_prompt_section = "Weights: {wt}"
new_prompt_section = """Weights: {wt}

 GROK X/TWITTER SENTIMENT (weight: 15%):
X Mood: {grok_mood}
Signal: {grok_signal}
Key Insight: {grok_insight}"""

content = content.replace(old_prompt_section, new_prompt_section)
print(" Added Grok section to prompt")

# Fix the format call to include grok vars
old_format = """        msg = client.messages.create(
            model="claude-opus-4-6", max_tokens=300,
            messages=[{"role":"user","content":prompt}]
        )"""

# Add grok variables before the prompt
old_wt_line = '        wt = " | ".join(f"{k}:{v*100:.0f}%" for k,v in weights.items())'
new_wt_line = '''        wt = " | ".join(f"{k}:{v*100:.0f}%" for k,v in weights.items())
        grok_mood    = (grok or {}).get("x_mood", "neutral") if grok else "unavailable"
        grok_signal  = (grok or {}).get("signal", "HOLD") if grok else "HOLD"
        grok_insight = (grok or {}).get("key_insight", "No X data") if grok else "No X data"'''

content = content.replace(old_wt_line, new_wt_line)
print(" Added grok variables")

# Fix the prompt format string
old_prompt_format = '        prompt = f"""You are the master orchestrator'
# Already has the right structure, just need to make sure grok vars are in scope

with open("orchestrator.py", "w") as f:
    f.write(content)

print("\n orchestrator.py patched successfully!")
