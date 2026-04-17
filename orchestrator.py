"""
ORCHESTRATOR v2  fixed: shared macro, None-safe onchain
"""

import anthropic
import datetime
import threading
from dotenv import load_dotenv
import os

from technical_agent import TechnicalAgent
from onchain_agent   import OnChainAgent
from news_fetcher         import get_latest_news
from grok_sentiment_agent import GrokSentimentAgent
from risk_manager    import RiskManager
from agent_memory    import AgentMemory

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class Orchestrator:
    DEFAULT_WEIGHTS = {"technical":0.35,"macro":0.25,"sentiment":0.25,"onchain":0.15}

    def __init__(self, total_capital=1000.0):
        self.technical    = TechnicalAgent()
        self.onchain      = OnChainAgent()
        self.memory       = AgentMemory()
        self.rm           = RiskManager(total_capital=total_capital)
        self.shared_macro = None
        print("\n Orchestrator online  all agents ready\n")

    def analyze(self, symbol):
        coin = symbol.replace("/USDT","")
        print(f"\n{'='*55}\n   ORCHESTRATOR: Analyzing {coin}\n{'='*55}")

        results = {}
        def run(name, fn):
            try: results[name] = fn()
            except Exception as e:
                print(f"   {name} failed: {e}")
                results[name] = None

        # Get price for Grok context
        _price = 0
        _fg    = ((self.shared_macro or {}).get("fear_greed") or {}).get("value", 50)

        threads = [
            threading.Thread(target=run, args=("technical", lambda: self.technical.analyze(symbol))),
            threading.Thread(target=run, args=("onchain",   lambda: self.onchain.analyze(symbol))),
            threading.Thread(target=run, args=("news",      lambda: {"text": get_latest_news()})),
            threading.Thread(target=run, args=("grok",      lambda: self.grok.analyze(symbol, _price, _fg))),
        ]
        for t in threads: t.start()
        for t in threads: t.join(timeout=30)

        tech    = results.get("technical")
        onchain = results.get("onchain")
        macro   = self.shared_macro
        news    = (results.get("news") or {}).get("text","No news")
        grok    = results.get("grok") or {}

        weights   = self._get_weights()
        consensus = self._compute_consensus(tech, macro, onchain, weights)
        raw_data  = tech["raw_data"] if tech else {}
        final     = self._ask_claude(symbol, raw_data, macro, onchain, news, consensus, weights, grok)

        price = raw_data.get("price", 0)
        approved, reason, details = self.rm.check_trade(final["action"], price, final["confidence"])

        signals = {
            "technical" : tech["signal"]    if tech    else "UNKNOWN",
            "sentiment" : "NEUTRAL",
            "macro"     : macro["signal"]   if macro   else "UNKNOWN",
            "onchain"   : onchain["signal"] if onchain else "UNKNOWN",
            "rsi"       : raw_data.get("rsi", 0),
            "fear_greed": ((macro or {}).get("fear_greed") or {}).get("value", 50),
        }

        for name, r in [("technical",tech),("onchain",onchain)]:
            if r:
                self.memory.record_signal(symbol, name, r["signal"],
                    self._c2f(r.get("confidence","low")), r.get("reasoning",""))

        return {
            "symbol": symbol, "action": final["action"],
            "confidence": final["confidence"], "reasoning": final["reasoning"],
            "risks": final["risks"], "price": price,
            "approved": approved, "risk_reason": reason,
            "trade_details": details if approved else {},
            "signals": signals, "consensus_score": consensus["score"],
            "weights": weights,
            "agents": {"technical":tech,"macro":macro,"onchain":onchain},
        }

    def _get_weights(self):
        creds = self.memory.get_agent_credibility()
        w = self.DEFAULT_WEIGHTS.copy()
        if creds:
            total = sum(v["score"] for v in creds.values() if v.get("total_calls",0)>=10)
            if total > 0:
                for a, d in creds.items():
                    if d.get("total_calls",0)>=10 and a in w:
                        w[a] = d["score"]/total
        t = sum(w.values())
        return {k: round(v/t,3) for k,v in w.items()}

    def _compute_consensus(self, tech, macro, onchain, weights):
        raw = {
            "technical": (tech["score"]/6)    if tech    else 0,
            "macro":     (macro["score"]/6)   if macro   else 0,
            "onchain":   (onchain["score"]/5) if onchain else 0,
            "sentiment": 0,
        }
        score = sum(raw[a]*weights.get(a,0) for a in raw)
        return {"score":round(score,3),
                "direction":"BUY" if score>0.15 else "SELL" if score<-0.15 else "HOLD",
                "raw":raw}

    def _ask_claude(self, symbol, data, macro, onchain, news, consensus, weights):
        coin = symbol.replace("/USDT","")

        macro_text = "Macro unavailable (rate limited  will retry next cycle)"
        if macro:
            fg = macro.get("fear_greed") or {}
            macro_text = (
                f"Regime: {macro.get('regime','?')} | Score: {macro.get('score',0):+d}\n"
                f"Fear & Greed: {fg.get('value','?')}/100 ({fg.get('label','?')})\n"
                f"BTC Dominance: {(macro.get('btc_dominance') or {}).get('btc_dominance','?')}%\n"
                f"ETF Flow: {(macro.get('etf_signal') or {}).get('signal','?')}"
            )

        onchain_text = "On-chain unavailable (rate limited)"
        if onchain:
            flow  = onchain.get("flow")  or {}
            whale = onchain.get("whale") or {}
            onchain_text = (
                f"Flow: {flow.get('signal','?')} | "
                f"Whale: {whale.get('signal','?')} | "
                f"{onchain.get('reasoning','')}"
            )

        wt = " | ".join(f"{k}:{v*100:.0f}%" for k,v in weights.items())
        grok_mood    = (grok or {}).get("x_mood", "neutral") if grok else "unavailable"
        grok_signal  = (grok or {}).get("signal", "HOLD") if grok else "HOLD"
        grok_insight = (grok or {}).get("key_insight", "No X data") if grok else "No X data"

        prompt = f"""You are the master orchestrator of a multi-agent crypto trading system.
Make the FINAL trading decision for {coin}/USDT.

 TECHNICAL (weight {weights['technical']*100:.0f}%):
Price: ${data.get('price',0):,.2f} | RSI 1h: {data.get('rsi',0):.1f} | RSI 4h: {data.get('rsi_4h',0):.1f}
MACD: {'Bullish' if data.get('macd',0)>data.get('macd_sig',0) else 'Bearish'}
BB: {'ABOVE upper ' if data.get('price',0)>data.get('bb_upper',0) else 'BELOW lower ' if data.get('price',0)<data.get('bb_lower',0) else 'Inside bands'}
Volume: {data.get('volume',0):,.0f} vs avg {data.get('vol_avg',0):,.0f} | 4H: {data.get('trend_4h','?')}
Consensus: {consensus['score']:+.3f}

 MACRO (weight {weights['macro']*100:.0f}%):
{macro_text}

 ON-CHAIN (weight {weights['onchain']*100:.0f}%):
{onchain_text}

 SENTIMENT:
{news[:500]}

Weights: {wt}

 GROK X/TWITTER SENTIMENT (weight: 15%):
X Mood: {grok_mood}
Signal: {grok_signal}
Key Insight: {grok_insight}

Respond EXACTLY:
ACTION: [BUY or SELL or HOLD]
CONFIDENCE: [high or medium or low]
REASONING: [2-3 sentences]
RISKS: [1-2 risks]

Rules: HOLD if data missing or signals conflict. Only trade when agents agree."""

        msg = client.messages.create(
            model="claude-opus-4-6", max_tokens=300,
            messages=[{"role":"user","content":prompt}]
        )
        return self._parse(msg.content[0].text)

    def _parse(self, text):
        a,c,r,ri = "HOLD","medium","",""
        for line in text.strip().splitlines():
            if line.startswith("ACTION:"):      a  = line.split(":",1)[1].strip().upper()
            elif line.startswith("CONFIDENCE:"): c  = line.split(":",1)[1].strip().lower()
            elif line.startswith("REASONING:"): r  = line.split(":",1)[1].strip()
            elif line.startswith("RISKS:"):     ri = line.split(":",1)[1].strip()
        return {"action":a,"confidence":c,"reasoning":r,"risks":ri}

    def _c2f(self, c): return {"high":0.9,"medium":0.6,"low":0.3}.get(c,0.5)

    def print_decision(self, result):
        a = result["action"]
        e = "" if a=="BUY" else "" if a=="SELL" else ""
        print(f"\n{''*55}")
        print(f"  {e} FINAL: {a} {result['symbol'].replace('/USDT','')}")
        print(f"  Confidence: {result['confidence'].upper()} | Score: {result['consensus_score']:+.3f}")
        print(f"  Price: ${result['price']:,.2f}")
        print(f"  Why:  {result['reasoning']}")
        print(f"  Risk: {result['risks']}")
        print(f"  {'' if result['approved'] else ''} {result['risk_reason']}")
        print(f"{''*55}\n")
