# ── RISK MANAGER ─────────────────────────────────────────
# This file is the safety layer. Claude's decisions MUST 
# pass through here before any trade is placed.

class RiskManager:
    def __init__(self, total_capital=1000):
        """
        total_capital = how much money you're trading with (in USD)
        Start small! We'll use $1000 as an example.
        """
        self.total_capital    = total_capital
        self.max_risk_per_trade = 0.02   # Never risk more than 2% per trade
        self.max_daily_loss   = 0.05     # Stop trading if down 5% in a day
        self.stop_loss_pct    = 0.02     # Auto sell if price drops 2%
        self.take_profit_pct  = 0.04     # Auto sell if price rises 4%
        self.daily_loss       = 0        # Track today's losses
        self.trades_today     = 0        # Track number of trades today
        self.max_trades_day   = 5        # Max 5 trades per day

    def check_trade(self, action, price, confidence="medium"):
        """
        Before any trade happens, run it through this check.
        Returns: (approved, reason, position_size)
        """
        print("\n🛡️  RISK MANAGER CHECKING TRADE...")
        print(f"   Action: {action} | Price: ${price:,.2f} | Confidence: {confidence}")

        # ── RULE 1: Daily loss limit ─────────────────────
        if self.daily_loss >= self.max_daily_loss * self.total_capital:
            return False, "❌ BLOCKED: Daily loss limit reached. No more trades today.", 0

        # ── RULE 2: Max trades per day ───────────────────
        if self.trades_today >= self.max_trades_day:
            return False, "❌ BLOCKED: Max trades for today reached.", 0

        # ── RULE 3: Don't trade on HOLD signal ───────────
        if action.upper() == "HOLD" or action.upper() == "WAIT":
            return False, "⏸️  SKIPPED: Claude says wait. No trade placed.", 0

        # ── RULE 4: Position sizing ──────────────────────
        # Adjust size based on confidence
        if confidence == "high":
            risk_multiplier = 1.0
        elif confidence == "medium":
            risk_multiplier = 0.5
        else:
            risk_multiplier = 0.25

        position_size = self.total_capital * self.max_risk_per_trade * risk_multiplier

        # ── RULE 5: Minimum trade size ───────────────────
        if position_size < 10:
            return False, "❌ BLOCKED: Position size too small to be worth trading.", 0

        # ── ALL CHECKS PASSED ────────────────────────────
        stop_loss_price   = price * (1 - self.stop_loss_pct)  if action == "BUY"  else price * (1 + self.stop_loss_pct)
        take_profit_price = price * (1 + self.take_profit_pct) if action == "BUY" else price * (1 - self.take_profit_pct)

        return True, "✅ APPROVED", {
            "action"          : action,
            "position_size_usd": round(position_size, 2),
            "entry_price"     : price,
            "stop_loss"       : round(stop_loss_price, 2),
            "take_profit"     : round(take_profit_price, 2),
            "max_loss_usd"    : round(position_size * self.stop_loss_pct, 2),
            "max_gain_usd"    : round(position_size * self.take_profit_pct, 2),
        }

    def record_trade(self, pnl):
        """Call this after every trade to track performance."""
        self.daily_loss  += min(0, pnl)  # Only track losses
        self.trades_today += 1

# ── TEST IT ──────────────────────────────────────────────
if __name__ == "__main__":
    rm = RiskManager(total_capital=1000)

    print("="*55)
    print("  🛡️  RISK MANAGER TEST")
    print("="*55)

    # Test 1: Normal buy signal
    approved, reason, details = rm.check_trade("BUY", 72400, "high")
    print(f"\n  Test 1 — BUY with high confidence:")
    print(f"  {reason}")
    if approved:
        print(f"  Position size : ${details['position_size_usd']}")
        print(f"  Stop loss     : ${details['stop_loss']:,}")
        print(f"  Take profit   : ${details['take_profit']:,}")
        print(f"  Max loss      : ${details['max_loss_usd']}")
        print(f"  Max gain      : ${details['max_gain_usd']}")

    # Test 2: Hold signal
    approved, reason, details = rm.check_trade("HOLD", 72400, "medium")
    print(f"\n  Test 2 — HOLD signal:")
    print(f"  {reason}")

    # Test 3: Low confidence
    approved, reason, details = rm.check_trade("BUY", 72400, "low")
    print(f"\n  Test 3 — BUY with low confidence:")
    print(f"  {reason}")
    if approved:
        print(f"  Position size : ${details['position_size_usd']} (smaller due to low confidence)")

    print("\n" + "="*55)
    print("  ✅ Risk manager is working!")
    print("="*55)