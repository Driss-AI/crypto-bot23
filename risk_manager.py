#  RISK MANAGER 
# Safety layer. Claude's decisions MUST pass through here.

class RiskManager:
    def __init__(self, total_capital=1000):
        self.total_capital      = total_capital
        self.max_risk_per_trade = 0.10   #  FIXED: was 0.02, too small for split capital
        self.max_daily_loss     = 0.05
        self.stop_loss_pct      = 0.02
        self.take_profit_pct    = 0.04
        self.daily_loss         = 0
        self.trades_today       = 0
        self.max_trades_day     = 20     #  FIXED: was 5, too restrictive for 3 styles  4 coins

    def check_trade(self, action, price, confidence="medium", style="scalp"):
        print("\n  RISK MANAGER CHECKING TRADE...")
        print(f"   Action: {action} | Price: ${price:,.2f} | Confidence: {confidence} | Style: {style}")

        #  RULE 1: Daily loss limit 
        if self.daily_loss >= self.max_daily_loss * self.total_capital:
            return False, " BLOCKED: Daily loss limit reached.", 0

        #  RULE 2: Max trades per day 
        if self.trades_today >= self.max_trades_day:
            return False, " BLOCKED: Max trades for today reached.", 0

        #  RULE 3: Don't trade on HOLD 
        if action.upper() in ("HOLD", "WAIT"):
            return False, "  SKIPPED: HOLD signal.", 0

        #  RULE 4: Position sizing 
        if confidence == "high":
            risk_multiplier = 1.0
        elif confidence == "medium":
            risk_multiplier = 0.5
        else:
            risk_multiplier = 0.25

        style_capital = {"scalp": self.total_capital * 0.40, "day": self.total_capital * 0.40, "swing": self.total_capital * 0.20}
        cap = style_capital.get(style, self.total_capital * 0.33)
        position_size = cap * self.max_risk_per_trade * risk_multiplier

        #  RULE 5: Minimum trade size 
        min_size = max(1.0, self.total_capital * 0.005)  #  FIXED: scales with capital
        if position_size < min_size:
            return False, f" BLOCKED: Position size ${position_size:.2f} too small.", 0

        #  ALL CHECKS PASSED 
        sl = price * (1 - self.stop_loss_pct)   if action == "BUY" else price * (1 + self.stop_loss_pct)
        tp = price * (1 + self.take_profit_pct) if action == "BUY" else price * (1 - self.take_profit_pct)

        return True, " APPROVED", {
            "action"           : action,
            "position_size_usd": round(position_size, 2),
            "entry_price"      : price,
            "stop_loss"        : round(sl, 2),
            "take_profit"      : round(tp, 2),
            "max_loss_usd"     : round(position_size * self.stop_loss_pct, 2),
            "max_gain_usd"     : round(position_size * self.take_profit_pct, 2),
        }

    def record_trade(self, pnl):
        self.daily_loss   += min(0, pnl)
        self.trades_today += 1


if __name__ == "__main__":
    rm = RiskManager(total_capital=50)  # Test with swing capital per coin
    print("="*55)
    approved, reason, details = rm.check_trade("BUY", 75000, "medium")
    print(f"Medium confidence: {reason}")
    if approved:
        print(f"  Size: ${details['position_size_usd']}")