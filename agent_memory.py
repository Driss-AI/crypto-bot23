"""
Agent Memory — PostgreSQL version
Survives Railway reboots, redeploys, crashes.
Falls back to SQLite if DATABASE_URL not set.
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Use PostgreSQL if available, else SQLite fallback
if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    USE_PG = True
    print("🐘 AgentMemory using PostgreSQL")
else:
    import sqlite3
    USE_PG = False
    DB_PATH = "memory/trades.db"
    print("📁 AgentMemory using SQLite (no DATABASE_URL found)")


def get_conn():
    if USE_PG:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    else:
        os.makedirs("memory", exist_ok=True)
        return sqlite3.connect(DB_PATH)


def placeholder(n=1):
    """Return correct placeholder for DB type."""
    if USE_PG:
        return ", ".join(["%s"] * n)
    else:
        return ", ".join(["?"] * n)


def ph():
    return "%s" if USE_PG else "?"


class AgentMemory:
    def __init__(self):
        self._init_database()
        print("🧠 AgentMemory loaded — database connected")

    def _init_database(self):
        conn = get_conn()
        c = conn.cursor()

        if USE_PG:
            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT, symbol TEXT, action TEXT,
                    entry_price REAL, exit_price REAL,
                    pnl REAL, pnl_pct REAL, status TEXT DEFAULT 'OPEN',
                    technical_signal TEXT, sentiment_signal TEXT,
                    macro_signal TEXT, onchain_signal TEXT,
                    rsi REAL, macd TEXT, fear_greed INTEGER,
                    volume_signal TEXT, claude_reasoning TEXT,
                    confidence TEXT, created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT, symbol TEXT, agent TEXT,
                    signal TEXT, confidence REAL, reasoning TEXT,
                    was_correct INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id SERIAL PRIMARY KEY,
                    pattern_key TEXT UNIQUE,
                    occurrences INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    avg_pnl REAL DEFAULT 0,
                    last_seen TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS agent_credibility (
                    id SERIAL PRIMARY KEY,
                    agent_name TEXT, market_regime TEXT,
                    score REAL DEFAULT 0.5,
                    total_calls INTEGER DEFAULT 0,
                    correct_calls INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(agent_name, market_regime)
                )
            """)
        else:
            c.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, symbol TEXT, action TEXT,
                    entry_price REAL, exit_price REAL,
                    pnl REAL, pnl_pct REAL, status TEXT DEFAULT 'OPEN',
                    technical_signal TEXT, sentiment_signal TEXT,
                    macro_signal TEXT, onchain_signal TEXT,
                    rsi REAL, macd TEXT, fear_greed INTEGER,
                    volume_signal TEXT, claude_reasoning TEXT,
                    confidence TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, symbol TEXT, agent TEXT,
                    signal TEXT, confidence REAL, reasoning TEXT,
                    was_correct INTEGER DEFAULT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_key TEXT UNIQUE,
                    occurrences INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    avg_pnl REAL DEFAULT 0,
                    last_seen TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS agent_credibility (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT, market_regime TEXT,
                    score REAL DEFAULT 0.5,
                    total_calls INTEGER DEFAULT 0,
                    correct_calls INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_name, market_regime)
                )
            """)

        conn.commit()
        conn.close()

    def record_signal(self, symbol, agent, signal, confidence, reasoning):
        conn = get_conn()
        c = conn.cursor()
        p = ph()
        c.execute(f"""
            INSERT INTO signals (timestamp, symbol, agent, signal, confidence, reasoning)
            VALUES ({p},{p},{p},{p},{p},{p})
        """, (datetime.now().isoformat(), symbol, agent, signal, confidence, reasoning))
        conn.commit()
        conn.close()

    def record_trade_entry(self, symbol, action, price, signals, reasoning, confidence):
        conn = get_conn()
        c = conn.cursor()
        p = ph()
        c.execute(f"""
            INSERT INTO trades
            (timestamp, symbol, action, entry_price,
             technical_signal, sentiment_signal, macro_signal, onchain_signal,
             rsi, fear_greed, claude_reasoning, confidence, status)
            VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},'OPEN')
        """, (
            datetime.now().isoformat(), symbol, action, price,
            signals.get("technical","UNKNOWN"), signals.get("sentiment","UNKNOWN"),
            signals.get("macro","UNKNOWN"), signals.get("onchain","UNKNOWN"),
            signals.get("rsi",0), signals.get("fear_greed",50),
            reasoning, confidence
        ))
        if USE_PG:
            c.execute("SELECT lastval()")
        else:
            c.execute("SELECT last_insert_rowid()")
        trade_id = c.fetchone()[0]
        conn.commit()
        conn.close()
        print(f"📈 Trade #{trade_id} recorded: {action} {symbol} @ ${price:,.2f}")
        return trade_id

    def record_trade_exit(self, trade_id, exit_price):
        conn = get_conn()
        c = conn.cursor()
        p = ph()
        c.execute(f"SELECT entry_price, action FROM trades WHERE id={p}", (trade_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        entry_price, action = row
        pnl     = exit_price - entry_price if action == "BUY" else entry_price - exit_price
        pnl_pct = (pnl / entry_price) * 100
        c.execute(f"""
            UPDATE trades SET exit_price={p}, pnl={p}, pnl_pct={p}, status='CLOSED'
            WHERE id={p}
        """, (exit_price, pnl, pnl_pct, trade_id))
        conn.commit()
        conn.close()
        self._learn_from_trade(trade_id)

    def _learn_from_trade(self, trade_id):
        conn = get_conn()
        c = conn.cursor()
        p = ph()
        c.execute(f"SELECT * FROM trades WHERE id={p}", (trade_id,))
        trade = c.fetchone()
        if not trade:
            conn.close()
            return

        pnl        = trade[6] or 0
        profitable = pnl > 0
        tech_sig   = trade[9]  or "UNKNOWN"
        sent_sig   = trade[10] or "UNKNOWN"
        macro_sig  = trade[11] or "UNKNOWN"
        chain_sig  = trade[12] or "UNKNOWN"

        pattern_key = f"tech:{tech_sig}|sent:{sent_sig}|macro:{macro_sig}|onchain:{chain_sig}"
        now = datetime.now().isoformat()

        if USE_PG:
            c.execute("""
                INSERT INTO patterns (pattern_key, occurrences, wins, total_pnl, win_rate, avg_pnl, last_seen)
                VALUES (%s,1,%s,%s,%s,%s,%s)
                ON CONFLICT(pattern_key) DO UPDATE SET
                    occurrences = patterns.occurrences + 1,
                    wins        = patterns.wins + %s,
                    total_pnl   = patterns.total_pnl + %s,
                    win_rate    = CAST(patterns.wins + %s AS REAL) / (patterns.occurrences + 1),
                    avg_pnl     = (patterns.total_pnl + %s) / (patterns.occurrences + 1),
                    last_seen   = %s
            """, (pattern_key, 1 if profitable else 0, pnl,
                  1.0 if profitable else 0.0, pnl, now,
                  1 if profitable else 0, pnl,
                  1 if profitable else 0, pnl, now))
        else:
            c.execute("""
                INSERT INTO patterns (pattern_key, occurrences, wins, total_pnl, win_rate, avg_pnl, last_seen)
                VALUES (?,1,?,?,?,?,?)
                ON CONFLICT(pattern_key) DO UPDATE SET
                    occurrences=occurrences+1, wins=wins+?,
                    total_pnl=total_pnl+?,
                    win_rate=CAST(wins+? AS REAL)/(occurrences+1),
                    avg_pnl=(total_pnl+?)/(occurrences+1), last_seen=?
            """, (pattern_key, 1 if profitable else 0, pnl,
                  1.0 if profitable else 0.0, pnl, now,
                  1 if profitable else 0, pnl,
                  1 if profitable else 0, pnl, now))

        for agent_name, signal in [("technical",tech_sig),("sentiment",sent_sig),
                                    ("macro",macro_sig),("onchain",chain_sig)]:
            was_correct = int(
                (signal in ["BUY","BULLISH"] and profitable) or
                (signal in ["SELL","BEARISH"] and not profitable)
            )
            if USE_PG:
                c.execute("""
                    INSERT INTO agent_credibility (agent_name, market_regime, score, total_calls, correct_calls)
                    VALUES (%s,'general',0.5,1,%s)
                    ON CONFLICT(agent_name,market_regime) DO UPDATE SET
                        total_calls   = agent_credibility.total_calls + 1,
                        correct_calls = agent_credibility.correct_calls + %s,
                        score         = CAST(agent_credibility.correct_calls+%s AS REAL)/(agent_credibility.total_calls+1)
                """, (agent_name, was_correct, was_correct, was_correct))
            else:
                c.execute("""
                    INSERT INTO agent_credibility (agent_name,market_regime,score,total_calls,correct_calls)
                    VALUES (?,'general',0.5,1,?)
                    ON CONFLICT(agent_name,market_regime) DO UPDATE SET
                        total_calls=total_calls+1, correct_calls=correct_calls+?,
                        score=CAST(correct_calls+? AS REAL)/(total_calls+1)
                """, (agent_name, was_correct, was_correct, was_correct))

        conn.commit()
        conn.close()

    def get_pattern_win_rate(self, tech, sent, macro, onchain):
        pattern_key = f"tech:{tech}|sent:{sent}|macro:{macro}|onchain:{onchain}"
        conn = get_conn()
        c = conn.cursor()
        p = ph()
        c.execute(f"""
            SELECT occurrences, wins, win_rate, avg_pnl
            FROM patterns WHERE pattern_key={p}
        """, (pattern_key,))
        row = c.fetchone()
        conn.close()
        if row:
            return {"occurrences":row[0],"win_rate":row[2],"avg_pnl":row[3],"reliable":row[0]>=5}
        return None

    def get_agent_credibility(self):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT agent_name, score, total_calls, correct_calls FROM agent_credibility")
        rows = c.fetchall()
        conn.close()
        return {r[0]: {"score":round(r[1],3),"total_calls":r[2],"correct_calls":r[3]} for r in rows}

    def get_stats(self):
        conn = get_conn()
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
        win_rate = (wins/total*100) if total > 0 else 0
        return {"total_trades":total,"wins":wins,"losses":total-wins,
                "win_rate":round(win_rate,1),"avg_pnl_pct":round(avg_pnl,2),
                "total_pnl":round(total_pnl,2),"patterns_discovered":patterns}

    def print_stats(self):
        stats = self.get_stats()
        creds = self.get_agent_credibility()
        print("\n" + "="*50)
        print("  🧠 BOT MEMORY STATS")
        print("="*50)
        print(f"  Total trades:     {stats['total_trades']}")
        print(f"  Win rate:         {stats['win_rate']}%")
        print(f"  Avg P&L:          {stats['avg_pnl_pct']:+.2f}%")
        print(f"  Total P&L:        ${stats['total_pnl']:+,.2f}")
        print(f"  Patterns learned: {stats['patterns_discovered']}")
        print("\n  Agent Credibility:")
        for agent, data in creds.items():
            bar = "█" * int(data['score'] * 10)
            print(f"  {agent:<12} {bar:<10} {data['score']:.2f} ({data['total_calls']} calls)")
        print("="*50 + "\n")
