"""
SCORING ENGINE v2 — Single Decision Authority
Based on:
  - Weighted Majority Algorithm (Littlestone & Warmuth, adapted by Numin 2024)
  - Meta-labeling principles (Lopez de Prado, AIFML 2018)
  - Regime-adaptive weighting (dynamic weights per market state)

Architecture:
  PRIMARY LAYER   → scoring engine aggregates all agent votes → score [-1, 1]
  META LAYER      → secondary filter decides: trade or skip (even if score qualifies)
  RISK LAYER      → risk_manager enforces position sizing + kill switches

Key design decisions (research-backed):
  1. Utility-based weight adaptation (profitability) not just accuracy
  2. Rolling 30-trade window — short windows outperform long ones (Numin 2024)
  3. Regime-specific static weights as fallback (no data = no dynamic tuning)
  4. Meta-filter blocks trades even at high scores when quality criteria fail
  5. Calibrated thresholds: ±0.70 high / ±0.55 medium — asymmetric only if data supports it

Score interpretation:
  +1.0 = all signals screaming BUY at maximum confidence
  -1.0 = all signals screaming SELL at maximum confidence
   0.0 = pure noise / conflicting signals = HOLD
"""

from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Minimum trades before dynamic weighting activates (per signal source)
MIN_TRADES_FOR_DYNAMIC = 30

# Rolling window size for utility calculation (Numin: short windows win)
ROLLING_WINDOW = 30

# Decision thresholds — symmetric until live data proves otherwise
THRESHOLD_HIGH   = 0.70
THRESHOLD_MEDIUM = 0.55

# Exponential decay for weight updates (higher = faster adaptation)
DECAY_FACTOR = 0.95   # each old trade contributes 0.95^n of its original weight

# Base weights per regime (must sum to 1.0 per regime)
# Research: trending → technical dominates; ranging → context signals matter more
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "TRENDING_UP": {
        "technical" : 0.45,
        "macro"     : 0.20,
        "sentiment" : 0.20,
        "whale"     : 0.15,
    },
    "TRENDING_DOWN": {
        "technical" : 0.45,
        "macro"     : 0.20,
        "sentiment" : 0.20,
        "whale"     : 0.15,
    },
    "RANGING": {
        "technical" : 0.25,
        "macro"     : 0.28,
        "sentiment" : 0.27,
        "whale"     : 0.20,
    },
    "CHOP": None,   # no trades — handled before reaching score()
}

SIGNAL_SOURCES = ["technical", "macro", "sentiment", "whale"]


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeOutcome:
    """One closed trade outcome for weight adaptation."""
    signal_source  : str
    predicted_score: float   # score this source contributed (+/-)
    actual_pnl     : float   # positive = win, negative = loss
    regime         : str

    @property
    def utility(self) -> float:
        """
        Utility metric (Numin 2024): did the signal contribute correctly?
        Better than raw accuracy — weights profitability, not just direction.
        """
        predicted_direction = 1.0 if self.predicted_score > 0 else -1.0
        actual_direction    = 1.0 if self.actual_pnl > 0 else -1.0
        # Correct direction = positive utility proportional to PnL magnitude
        if predicted_direction == actual_direction:
            return min(1.0, abs(self.actual_pnl) / 10.0)  # cap at 1.0
        else:
            return -min(1.0, abs(self.actual_pnl) / 10.0)  # penalize wrong calls


@dataclass
class SignalRecord:
    """Rolling performance tracker per signal source."""
    source   : str
    outcomes : deque = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))

    def add(self, outcome: TradeOutcome):
        self.outcomes.append(outcome)

    def weighted_utility(self) -> float | None:
        """Exponentially weighted utility — recent trades matter more."""
        if len(self.outcomes) < 5:
            return None  # not enough data
        total_weight = 0.0
        total_utility = 0.0
        for i, outcome in enumerate(reversed(self.outcomes)):
            w = DECAY_FACTOR ** i
            total_utility += outcome.utility * w
            total_weight  += w
        return total_utility / total_weight if total_weight > 0 else 0.0

    def win_rate(self) -> float | None:
        if len(self.outcomes) < 5:
            return None
        wins = sum(1 for o in self.outcomes if o.utility > 0)
        return wins / len(self.outcomes)

    def profit_factor(self) -> float | None:
        if len(self.outcomes) < 5:
            return None
        gains  = sum(o.actual_pnl for o in self.outcomes if o.actual_pnl > 0)
        losses = abs(sum(o.actual_pnl for o in self.outcomes if o.actual_pnl < 0))
        return gains / losses if losses > 0 else (2.0 if gains > 0 else 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# META-LABEL FILTER
# ─────────────────────────────────────────────────────────────────────────────

class MetaFilter:
    """
    Secondary decision layer (meta-labeling principle, Lopez de Prado 2018).

    The scoring engine gives direction + score.
    The meta-filter decides: trade or skip?

    This is NOT a signal generator — it only filters out low-quality entries
    even when the primary score qualifies. It answers one binary question:
    "Given this score and these conditions, should we actually trade?"

    Rule-based at this stage (no ML — insufficient data).
    Will evolve to statistical classifier after 200+ closed trades.
    """

    def evaluate(
        self,
        action      : str,
        score       : float,
        regime      : dict,
        agent_result: dict,
        style       : str,
        breakdown   : dict,
    ) -> tuple[bool, str]:
        """
        Returns (should_trade: bool, reason: str).
        """
        raw_data = agent_result.get("raw_data", {})
        rsi_1h   = raw_data.get("rsi", 50)
        rsi_4h   = raw_data.get("rsi_4h", 50)
        trend_4h = raw_data.get("trend_4h", "UNKNOWN")
        trend_1d = raw_data.get("trend_1d", "UNKNOWN")
        adx      = regime.get("adx", 20)

        # ── Gate 1: Signal coherence ──────────────────────────────────────────
        # At least 2 of 4 signal sources must agree with the direction
        direction = 1 if action == "BUY" else -1
        agreeing = sum(1 for v in breakdown.values() if v * direction > 0.05)
        if agreeing < 2:
            return False, f"Only {agreeing}/4 signals agree — low coherence ❌"

        # ── Gate 2: No counter-trend entries ─────────────────────────────────
        # Never buy if 1D is BEARISH AND 4H is BEARISH simultaneously
        if action == "BUY" and trend_1d == "BEARISH" and trend_4h == "BEARISH":
            return False, "BUY against both 1D + 4H downtrend — blocked ❌"
        if action == "SELL" and trend_1d == "BULLISH" and trend_4h == "BULLISH":
            return False, "SELL against both 1D + 4H uptrend — blocked ❌"

        # ── Gate 3: RSI extremes on the wrong side ────────────────────────────
        # Don't buy when already deeply overbought on both timeframes
        if action == "BUY" and rsi_1h > 80 and rsi_4h > 75:
            return False, f"BUY with RSI 1h={rsi_1h:.0f} 4h={rsi_4h:.0f} — overbought ❌"
        if action == "SELL" and rsi_1h < 20 and rsi_4h < 25:
            return False, f"SELL with RSI 1h={rsi_1h:.0f} 4h={rsi_4h:.0f} — oversold ❌"

        # ── Gate 4: Swing-specific — require stronger score ───────────────────
        # Swing trades sit open for days — higher bar justified
        if style == "swing" and abs(score) < 0.60:
            return False, f"Swing score {score:+.3f} below 0.60 minimum ❌"

        # ── Gate 5: ADX confirmation for trend entries ────────────────────────
        if style == "day" and adx < 18:
            return False, f"ADX {adx:.1f} < 18 — trend too weak for day trade ❌"

        # ── Gate 6: Technical signal must not be HOLD when scoring BUY/SELL ──
        tech_score = breakdown.get("technical", 0)
        if action == "BUY"  and tech_score < -0.20:
            return False, f"Technical NEGATIVE ({tech_score:+.2f}) while scoring BUY ❌"
        if action == "SELL" and tech_score > 0.20:
            return False, f"Technical POSITIVE ({tech_score:+.2f}) while scoring SELL ❌"

        return True, "All meta-filter gates passed ✅"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCORING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ScoringEngine:

    def __init__(self):
        self.name        = "scoring_engine"
        self.meta_filter = MetaFilter()
        self._trackers   = {src: SignalRecord(source=src) for src in SIGNAL_SOURCES}
        print("✅ Scoring Engine v2 initialized")
        print(f"   Dynamic weighting activates after {MIN_TRADES_FOR_DYNAMIC} closed trades per source")

    # ── PRIMARY INTERFACE ─────────────────────────────────────────────────────

    def score(
        self,
        technical : dict,
        regime    : dict,
        style     : str,
        macro     : dict | None = None,
        grok      : dict | None = None,
        whale     : dict | None = None,
        news      : str  | None = None,
    ) -> dict:
        """
        Aggregate all agent signals → single weighted score → decision + meta-filter.

        Returns:
            action, confidence, score, breakdown, weights, regime, meta_passed, reasons
        """
        regime_name = regime.get("regime", "RANGING")

        # CHOP gate — instant HOLD before any computation
        if regime_name == "CHOP" or not regime.get("tradeable", True):
            return self._hold(regime_name, "⛔ Regime=CHOP — no trades in choppy markets")

        # Style gate — day trades need trending regime
        if style == "day" and not regime.get("day_ok", True):
            return self._hold(regime_name, f"⛔ {regime_name} not suitable for day trading")

        # ── Step 1: Normalize each source to [-1, 1] ──────────────────────────
        breakdown = {
            "technical" : self._norm_technical(technical),
            "macro"     : self._norm_macro(macro),
            "sentiment" : self._norm_sentiment(grok, news),
            "whale"     : self._norm_whale(whale),
        }

        # ── Step 2: Get weights (static or dynamic) ───────────────────────────
        weights = self._get_weights(regime_name)

        # ── Step 3: Weighted sum → final score ────────────────────────────────
        final_score = sum(breakdown[src] * weights[src] for src in SIGNAL_SOURCES)
        final_score = max(-1.0, min(1.0, final_score))  # hard clamp

        # ── Step 4: Threshold → action ────────────────────────────────────────
        if final_score >= THRESHOLD_HIGH:
            action, confidence = "BUY", "high"
        elif final_score >= THRESHOLD_MEDIUM:
            action, confidence = "BUY", "medium"
        elif final_score <= -THRESHOLD_HIGH:
            action, confidence = "SELL", "high"
        elif final_score <= -THRESHOLD_MEDIUM:
            action, confidence = "SELL", "medium"
        else:
            return self._hold(
                regime_name,
                f"Score {final_score:+.3f} within ±{THRESHOLD_MEDIUM} dead zone — HOLD"
            )

        # ── Step 5: Meta-filter (secondary layer) ─────────────────────────────
        meta_ok, meta_reason = self.meta_filter.evaluate(
            action=action,
            score=final_score,
            regime=regime,
            agent_result=technical,
            style=style,
            breakdown=breakdown,
        )

        if not meta_ok:
            return self._hold(regime_name, f"Meta-filter blocked: {meta_reason}")

        # ── Step 6: Build output ───────────────────────────────────────────────
        reasons = self._build_reasons(breakdown, weights, regime_name, final_score)
        reasons.append(f"✅ Meta-filter: {meta_reason}")

        result = {
            "action"      : action,
            "confidence"  : confidence,
            "score"       : round(final_score, 4),
            "breakdown"   : {k: round(v, 4) for k, v in breakdown.items()},
            "weights"     : {k: round(v, 4) for k, v in weights.items()},
            "regime"      : regime_name,
            "meta_passed" : True,
            "reasons"     : reasons,
        }

        emoji = "🟢" if action == "BUY" else "🔴"
        print(
            f"  📊 Score {final_score:+.4f} → {emoji} {action} ({confidence}) | "
            f"T={breakdown['technical']:+.3f} M={breakdown['macro']:+.3f} "
            f"S={breakdown['sentiment']:+.3f} W={breakdown['whale']:+.3f}"
        )
        return result

    # ── FEEDBACK / ADAPTATION ─────────────────────────────────────────────────

    def record_closed_trade(
        self,
        breakdown : dict,
        regime    : str,
        actual_pnl: float,
    ):
        """
        Called after a trade closes. Records outcome per source for weight adaptation.
        This is the feedback loop that makes weights adaptive over time.
        """
        for source in SIGNAL_SOURCES:
            predicted_score = breakdown.get(source, 0.0)
            outcome = TradeOutcome(
                signal_source   = source,
                predicted_score = predicted_score,
                actual_pnl      = actual_pnl,
                regime          = regime,
            )
            self._trackers[source].add(outcome)

    def get_signal_stats(self) -> dict:
        """Performance stats per signal source — used in daily Telegram report."""
        stats = {}
        for source, tracker in self._trackers.items():
            wu  = tracker.weighted_utility()
            wr  = tracker.win_rate()
            pf  = tracker.profit_factor()
            n   = len(tracker.outcomes)
            stats[source] = {
                "trades"          : n,
                "weighted_utility": round(wu, 3) if wu is not None else None,
                "win_rate"        : round(wr * 100, 1) if wr is not None else None,
                "profit_factor"   : round(pf, 2) if pf is not None else None,
                "dynamic_active"  : n >= MIN_TRADES_FOR_DYNAMIC,
            }
        return stats

    def get_current_weights(self, regime: str = "TRENDING_UP") -> dict:
        """Returns the weights that would be used right now (static or dynamic)."""
        return self._get_weights(regime)

    def format_stats_for_telegram(self) -> str:
        """Ready-to-send Telegram string with signal performance."""
        stats = self.get_signal_stats()
        lines = ["📡 Signal Performance:"]
        for source, s in stats.items():
            n   = s["trades"]
            wr  = f"{s['win_rate']:.0f}%" if s["win_rate"] else "N/A"
            pf  = f"{s['profit_factor']:.2f}" if s["profit_factor"] else "N/A"
            dyn = "🔄" if s["dynamic_active"] else f"⏳ {MIN_TRADES_FOR_DYNAMIC-n} more"
            lines.append(f"  {source:12}: {wr} WR | PF {pf} | {n} trades {dyn}")
        return "\n".join(lines)

    # ── NORMALIZATION ─────────────────────────────────────────────────────────

    def _norm_technical(self, tech: dict) -> float:
        """
        technical_agent produces a score typically in [-12, +12].
        Normalize with soft sigmoid-like clamp (not hard clip) to preserve
        the difference between +4 and +10 rather than both clipping to 1.0.
        """
        if not tech:
            return 0.0
        raw = float(tech.get("score", 0))
        # tanh gives smooth [-1, 1] with meaningful gradation
        return math.tanh(raw / 6.0)   # tanh(6/6)=0.76, tanh(12/6)=0.96

    def _norm_macro(self, macro: dict | None) -> float:
        if not macro:
            return 0.0

        points = 0.0

        # Macro regime score (typically -10 to +10)
        macro_score = float(macro.get("score", 0))
        points += math.tanh(macro_score / 5.0) * 0.5

        # Fear & Greed Index
        fg = (macro.get("fear_greed") or {}).get("value", 50)
        try:
            fg = float(fg)
            # Extreme fear (<25) = contrarian BUY signal
            # Extreme greed (>75) = contrarian SELL signal
            # Map 0-100 → contribution:  0→+0.4,  25→+0.2,  50→0,  75→-0.2,  100→-0.4
            fg_contribution = -(fg - 50) / 125.0
            points += fg_contribution
        except (TypeError, ValueError):
            pass

        # BTC dominance as regime signal (if available)
        btc_dom = macro.get("btc_dominance", 0)
        if btc_dom:
            try:
                # Rising dominance = risk-off (favor BTC shorts or stablecoin)
                # Falling dominance = alt season / risk-on
                btc_dom = float(btc_dom)
                dom_signal = -(btc_dom - 50) / 100.0   # mild contribution
                points += dom_signal * 0.3
            except (TypeError, ValueError):
                pass

        return max(-1.0, min(1.0, points))

    def _norm_sentiment(self, grok: dict | None, news: str | None) -> float:
        """
        Combine Grok structured vote + news keyword score.
        Grok gets 65% weight, news gets 35% — Grok has explicit direction signal.
        """
        grok_score = 0.0
        news_score = 0.0
        has_grok   = False
        has_news   = False

        if grok:
            vote = grok.get("vote", "HOLD").upper()
            conf = grok.get("confidence", "low").lower()
            conf_mult = {"high": 1.0, "medium": 0.65, "low": 0.30}.get(conf, 0.30)
            if vote == "BUY":
                grok_score = 1.0 * conf_mult
            elif vote == "SELL":
                grok_score = -1.0 * conf_mult
            has_grok = True

        if news and len(news) > 10:
            news_lower = news.lower()
            # Weighted keyword lists (more specific = higher weight)
            bull_signals = {
                "institutional inflow": 3, "etf approval": 3, "halving": 2,
                "bullish": 2, "surge": 2, "rally": 2, "ath": 2,
                "adoption": 1, "accumulate": 1, "inflow": 1, "breakout": 1,
            }
            bear_signals = {
                "sec enforcement": 3, "exchange hack": 3, "ban": 3,
                "bearish": 2, "crash": 2, "dump": 2, "outflow": 2,
                "regulation": 1, "sell-off": 1, "liquidation": 1, "fear": 1,
            }
            bull_total = sum(w for kw, w in bull_signals.items() if kw in news_lower)
            bear_total = sum(w for kw, w in bear_signals.items() if kw in news_lower)
            total = bull_total + bear_total
            if total > 0:
                news_score = (bull_total - bear_total) / (total + 2)  # +2 = Laplace smoothing
                has_news = True

        # Weighted combination
        if has_grok and has_news:
            combined = grok_score * 0.65 + news_score * 0.35
        elif has_grok:
            combined = grok_score
        elif has_news:
            combined = news_score * 0.6  # lower confidence without Grok
        else:
            combined = 0.0

        return max(-1.0, min(1.0, combined))

    def _norm_whale(self, whale: dict | None) -> float:
        """
        Normalize whale data to [-1, 1].
        Exchange inflows = bearish (whales preparing to sell).
        Exchange outflows = bullish (whales accumulating / hodling).
        """
        if not whale:
            return 0.0

        points = 0.0

        # Net exchange flow (negative = outflow = bullish)
        net_flow    = float(whale.get("net_flow", 0))
        large_buys  = float(whale.get("large_buys", 0))
        large_sells = float(whale.get("large_sells", 0))
        alert_type  = whale.get("alert_type", "")

        # Normalize net flow (inflow to exchanges = bearish)
        if net_flow != 0:
            # Use tanh with a reference scale of 500 BTC
            points -= math.tanh(net_flow / 500.0) * 0.5

        # Large trade balance
        total_large = large_buys + large_sells
        if total_large > 0:
            whale_direction = (large_buys - large_sells) / total_large
            points += whale_direction * 0.5

        # Alert-type boost
        if "accumulation" in str(alert_type).lower():
            points += 0.3
        elif "distribution" in str(alert_type).lower():
            points -= 0.3

        return max(-1.0, min(1.0, points))

    # ── WEIGHT MANAGEMENT ─────────────────────────────────────────────────────

    def _get_weights(self, regime_name: str) -> dict[str, float]:
        """
        Returns weights for this regime.
        Uses dynamic (utility-based) weights if enough data, else static.
        """
        static = REGIME_WEIGHTS.get(regime_name, REGIME_WEIGHTS["RANGING"])
        if static is None:
            static = REGIME_WEIGHTS["RANGING"]

        # Check if all sources have enough data for dynamic weights
        all_sources_ready = all(
            len(self._trackers[src].outcomes) >= MIN_TRADES_FOR_DYNAMIC
            for src in SIGNAL_SOURCES
        )

        if not all_sources_ready:
            return static.copy()

        # ── Dynamic weighting via Weighted Majority Algorithm ─────────────────
        # Base: regime static weights × exp(weighted_utility)
        # This preserves regime-awareness while adapting to signal performance
        dynamic = {}
        for src in SIGNAL_SOURCES:
            wu = self._trackers[src].weighted_utility() or 0.0
            # Boost factor: good utility → higher weight, bad → lower
            # exp(wu) in range [exp(-1), exp(1)] = [0.37, 2.72]
            boost = math.exp(max(-1.0, min(1.0, wu)))
            dynamic[src] = static[src] * boost

        # Normalize so weights sum to 1.0
        total = sum(dynamic.values())
        if total > 0:
            return {k: v / total for k, v in dynamic.items()}
        return static.copy()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _hold(self, regime: str, reason: str) -> dict:
        return {
            "action"      : "HOLD",
            "confidence"  : "low",
            "score"       : 0.0,
            "breakdown"   : {k: 0.0 for k in SIGNAL_SOURCES},
            "weights"     : REGIME_WEIGHTS.get(regime) or REGIME_WEIGHTS["RANGING"],
            "regime"      : regime,
            "meta_passed" : False,
            "reasons"     : [reason],
        }

    def _build_reasons(
        self,
        breakdown  : dict,
        weights    : dict,
        regime     : str,
        final_score: float,
    ) -> list[str]:
        sources = SIGNAL_SOURCES
        lines = [f"Regime: {regime} | Final score: {final_score:+.4f}"]
        for src in sources:
            s = breakdown[src]
            w = weights[src]
            c = s * w
            bar = "🟢" if s > 0.25 else "🔴" if s < -0.25 else "⚪"
            dyn_flag = "🔄" if len(self._trackers[src].outcomes) >= MIN_TRADES_FOR_DYNAMIC else ""
            lines.append(
                f"{bar} {src:12}: {s:+.3f} × {w:.0%} = {c:+.3f} {dyn_flag}"
            )
        return lines


# ── Module-level singleton ────────────────────────────────────────────────────
scoring_engine = ScoringEngine()


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from regime_detector import RegimeDetector

    eng = ScoringEngine()
    det = RegimeDetector()

    mock_tech   = {"score": 7, "signal": "BUY",
                   "raw_data": {"rsi": 48, "rsi_4h": 52, "trend_4h": "BULLISH", "trend_1d": "BULLISH"}}
    mock_macro  = {"score": 4, "regime": "BULLISH", "fear_greed": {"value": 32, "label": "Fear"}, "btc_dominance": 52}
    mock_grok   = {"vote": "BUY", "confidence": "high", "reasoning": "Strong X inflows"}
    mock_whale  = {"net_flow": -300, "large_buys": 9, "large_sells": 2, "alert_type": "accumulation"}
    mock_regime = {"regime": "TRENDING_UP", "tradeable": True, "day_ok": True, "swing_ok": True, "adx": 28}
    mock_news   = "Bitcoin ETF sees record institutional inflow as rally continues and adoption grows"

    print("\n" + "="*60)
    print("SCORING ENGINE v2 — Test Run")
    print("="*60)

    for style in ["day", "swing"]:
        print(f"\n── {style.upper()} ──")
        result = eng.score(
            technical=mock_tech,
            regime=mock_regime,
            style=style,
            macro=mock_macro,
            grok=mock_grok,
            whale=mock_whale,
            news=mock_news,
        )
        print(f"Decision:    {result['action']} ({result['confidence']})")
        print(f"Score:       {result['score']:+.4f}")
        print(f"Meta passed: {result['meta_passed']}")
        print("Breakdown:")
        for src, val in result["breakdown"].items():
            w = result["weights"][src]
            print(f"  {src:12}: {val:+.3f} × {w:.0%} = {val*w:+.3f}")
        print("\nReasons:")
        for r in result["reasons"]:
            print(f"  {r}")

    # Simulate 5 trade outcomes to test adaptation
    print("\n── Simulating 5 trade outcomes ──")
    mock_breakdown = {"technical": 0.6, "macro": 0.3, "sentiment": 0.4, "whale": 0.2}
    for i, pnl in enumerate([12, -8, 15, 20, -5]):
        eng.record_closed_trade(mock_breakdown, "TRENDING_UP", pnl)
    print(eng.format_stats_for_telegram())
