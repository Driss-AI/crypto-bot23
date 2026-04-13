import sqlite3
import json
import os
from datetime import datetime

# Database lives in the memory folder
DB_PATH = os.path.join(os.path.dirname(__file__), "../memory/trades.db")

class AgentMemory:
    """
    Persistent memory for the entire trading system.
    Survives restarts, crashes, everything.
    Gets smarter with every trade.
    """

    def __init__(self):
        self.db_path = DB_PATH
        self._init_database()
        print("🧠 AgentMemory loaded — database connected")

    def _init_database(self):
        """Create all tables if they don't exist yet"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Every trade ever made
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT,
                symbol          TEXT,
                action          TEXT,
                entry_price     REAL,
                exit_price      REAL,
                pnl             REAL,
                pnl_pct         REAL,
                status          TEXT DEFAULT 'OPEN',
                technical_signal TEXT,
                sentiment_signal TEXT,
                macro_signal    TEXT,
                onchain_signal  TEXT,
                rsi             REAL,
                macd            TEXT,
                fear_greed      INTEGER,
                volume_signal   TEXT,
                claude_reasoning TEXT,
                confidence      TEXT,
                created_at      TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Every signal ever generated
        c.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT,
                symbol      TEXT,
                agent       TEXT,
                signal      TEXT,
                confidence  REAL,
                reasoning   TEXT,
                was_correct INTEGER DEFAULT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Discovered patterns
        c.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_key TEXT UNIQUE,
                occurrences INTEGER DEFAULT 0,
                wins        INTEGER DEFAULT 0,
                total_pnl   REAL DEFAULT 0,
                win_rate    REAL DEFAULT 0,
                avg_pnl     REAL DEFAULT 0,
                last_seen   TEXT,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Agent credibility scores over time
        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_credibility (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name  TEXT,
                market_regime TEXT,
                score       REAL DEFAULT 0.5,
                total_calls INTEGER DEFAULT 0,
                correct_calls INTEGER DEFAULT 0,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(agent_name, market_regime)
            )
        """)

        # Weekly learning reviews
        c.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                week        TEXT,
                claude_analysis TEXT,
                key_learnings TEXT,
                rule_changes TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    # ── TRADE RECORDING ─────────────────────────────────────

    def record_signal(self, symbol, agent, signal, confidence, reasoning):
        """Save every signal — win or lose — for learning later"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO signals 
            (timestamp, symbol, agent, signal, confidence, reasoning)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), symbol, agent, 
              signal, confidence, reasoning))
        conn.commit()
        conn.close()
        print(f"📝 Signal recorded: {agent} → {signal} ({confidence} confidence)")

    def record_trade_entry(self, symbol, action, price, signals, reasoning, confidence):
        """Called when bot decides to place a trade"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO trades 
            (timestamp, symbol, action, entry_price, 
             technical_signal, sentiment_signal, 
             macro_signal, onchain_signal,
             rsi, fear_greed, claude_reasoning, confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """, (
            datetime.now().isoformat(),
            symbol, action, price,
            signals.get("technical", "UNKNOWN"),
            signals.get("sentiment", "UNKNOWN"),
            signals.get("macro", "UNKNOWN"),
            signals.get("onchain", "UNKNOWN"),
            signals.get("rsi", 0),
            signals.get("fear_greed", 50),
            reasoning, confidence
        ))
        trade_id = c.lastrowid
        conn.commit()
        conn.close()
        print(f"📈 Trade #{trade_id} recorded: {action} {symbol} @ ${price:,.2f}")
        return trade_id

    def record_trade_exit(self, trade_id, exit_price):
        """Called when trade closes — triggers learning"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Get the entry price
        c.execute("SELECT entry_price, action FROM trades WHERE id = ?", (trade_id,))
        row = c.fetchone()
        if not row:
            print(f"⚠️ Trade #{trade_id} not found!")
            conn.close()
            return

        entry_price, action = row
        if action == "BUY":
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price

        pnl_pct = (pnl / entry_price) * 100

        # Update trade record
        c.execute("""
            UPDATE trades 
            SET exit_price=?, pnl=?, pnl_pct=?, status='CLOSED'
            WHERE id=?
        """, (exit_price, pnl, pnl_pct, trade_id))

        conn.commit()
        conn.close()

        result = "✅ PROFIT" if pnl > 0 else "❌ LOSS"
        print(f"{result} Trade #{trade_id} closed: {pnl_pct:+.2f}%")

        # Learn from this trade
        self._learn_from_trade(trade_id)

    # ── LEARNING ────────────────────────────────────────────

    def _learn_from_trade(self, trade_id):
        """After every trade closes — update patterns and credibility"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        trade = c.fetchone()
        if not trade:
            conn.close()
            return

        # Unpack trade data
        (id_, timestamp, symbol, action, entry_price, exit_price,
         pnl, pnl_pct, status, tech_sig, sent_sig, macro_sig,
         onchain_sig, rsi, macd, fear_greed, vol_sig,
         reasoning, confidence, created_at) = trade

        profitable = pnl > 0

        # Build pattern key from signal combination
        pattern_key = f"tech:{tech_sig}|sent:{sent_sig}|macro:{macro_sig}|onchain:{onchain_sig}"

        # Update pattern library
        c.execute("""
            INSERT INTO patterns (pattern_key, occurrences, wins, total_pnl, win_rate, avg_pnl, last_seen)
            VALUES (?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(pattern_key) DO UPDATE SET
                occurrences = occurrences + 1,
                wins = wins + ?,
                total_pnl = total_pnl + ?,
                win_rate = CAST(wins + ? AS REAL) / (occurrences + 1),
                avg_pnl = (total_pnl + ?) / (occurrences + 1),
                last_seen = ?,
                updated_at = CURRENT_TIMESTAMP
        """, (
            pattern_key,
            1 if profitable else 0,
            pnl, 
            1.0 if profitable else 0.0,
            pnl,
            datetime.now().isoformat(),
            1 if profitable else 0,
            pnl,
            1 if profitable else 0,
            pnl,
            datetime.now().isoformat()
        ))

        # Update agent credibility scores
        agents = {
            "technical": tech_sig,
            "sentiment": sent_sig,
            "macro": macro_sig,
            "onchain": onchain_sig
        }

        for agent_name, signal in agents.items():
            was_correct = (
                (signal in ["BUY", "BULLISH"] and profitable) or
                (signal in ["SELL", "BEARISH"] and not profitable)
            )

            c.execute("""
                INSERT INTO agent_credibility (agent_name, market_regime, score, total_calls, correct_calls)
                VALUES (?, 'general', 0.5, 1, ?)
                ON CONFLICT(agent_name, market_regime) DO UPDATE SET
                    total_calls = total_calls + 1,
                    correct_calls = correct_calls + ?,
                    score = CAST(correct_calls + ? AS REAL) / (total_calls + 1),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                agent_name,
                1 if was_correct else 0,
                1 if was_correct else 0,
                1 if was_correct else 0
            ))

        conn.commit()
        conn.close()
        print(f"🧠 Learning complete — patterns and credibility updated")

    # ── QUERYING ────────────────────────────────────────────

    def get_pattern_win_rate(self, tech, sent, macro, onchain):
        """Before a trade — check if this signal combo worked before"""
        pattern_key = f"tech:{tech}|sent:{sent}|macro:{macro}|onchain:{onchain}"
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT occurrences, wins, win_rate, avg_pnl 
            FROM patterns WHERE pattern_key = ?
        """, (pattern_key,))
        row = c.fetchone()
        conn.close()

        if row:
            occurrences, wins, win_rate, avg_pnl = row
            return {
                "occurrences": occurrences,
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "reliable": occurrences >= 5
            }
        return None

    def get_agent_credibility(self):
        """Get current trust scores for all agents"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT agent_name, score, total_calls, correct_calls 
            FROM agent_credibility
        """)
        rows = c.fetchall()
        conn.close()

        result = {}
        for agent_name, score, total, correct in rows:
            result[agent_name] = {
                "score": round(score, 3),
                "total_calls": total,
                "correct_calls": correct
            }
        return result

    def get_best_patterns(self, min_occurrences=5):
        """Return the most reliable signal combinations"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT pattern_key, occurrences, win_rate, avg_pnl
            FROM patterns
            WHERE occurrences >= ?
            ORDER BY win_rate DESC
            LIMIT 10
        """, (min_occurrences,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_recent_trades(self, limit=10):
        """Get last N trades for review"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            SELECT id, timestamp, symbol, action, 
                   entry_price, exit_price, pnl_pct, status
            FROM trades
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_stats(self):
        """Overall bot performance summary"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'")
        total = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND pnl > 0")
        wins = c.fetchone()[0]

        c.execute("SELECT AVG(pnl_pct) FROM trades WHERE status='CLOSED'")
        avg_pnl = c.fetchone()[0] or 0

        c.execute("SELECT SUM(pnl) FROM trades WHERE status='CLOSED'")
        total_pnl = c.fetchone()[0] or 0

        c.execute("SELECT COUNT(*) FROM patterns")
        patterns = c.fetchone()[0]

        conn.close()

        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "patterns_discovered": patterns
        }

    def print_stats(self):
        """Print a nice summary to terminal"""
        stats = self.get_stats()
        creds = self.get_agent_credibility()

        print("\n" + "="*50)
        print("  🧠 BOT MEMORY STATS")
        print("="*50)
        print(f"  Total trades:      {stats['total_trades']}")
        print(f"  Win rate:          {stats['win_rate']}%")
        print(f"  Avg P&L per trade: {stats['avg_pnl_pct']:+.2f}%")
        print(f"  Total P&L:         ${stats['total_pnl']:+,.2f}")
        print(f"  Patterns learned:  {stats['patterns_discovered']}")
        print("\n  Agent Credibility:")
        for agent, data in creds.items():
            bar = "█" * int(data['score'] * 10)
            print(f"  {agent:<12} {bar:<10} {data['score']:.2f} ({data['total_calls']} calls)")
        print("="*50 + "\n")