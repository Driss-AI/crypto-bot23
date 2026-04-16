"""
WEEKLY PERFORMANCE REVIEW
Runs automatically inside Railway every 7 days.
"""
import os, psycopg2, anthropic, requests
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHAT   = os.getenv("TELEGRAM_CHAT_ID")

def tg(msg):
    if not TOKEN or not CHAT:
        print("No Telegram config")
        return
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT, "text": msg, "parse_mode": "HTML"}, timeout=15)

# Use Railway internal DB — never times out
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur  = conn.cursor()
cur.execute("""
    SELECT action, entry_price, exit_price, pnl, confidence, timestamp
    FROM paper_trades
    WHERE status='CLOSED' AND pnl IS NOT NULL
    ORDER BY id DESC LIMIT 50
""")
trades = cur.fetchall()
conn.close()

if not trades:
    tg("📊 <b>Weekly Review</b>\n\nNo closed trades yet.")
    print("No trades yet.")
    exit()

wins  = [t for t in trades if t[3] and t[3] > 0]
total = sum(t[3] for t in trades if t[3])
wr    = len(wins)/len(trades)*100

trade_list = "\n".join([
    f"{'✅' if t[3] and t[3]>0 else '❌'} {t[0]} ${t[1]:.2f} pnl:${t[3]:.2f} ({t[4]})"
    for t in trades[:20]
])

resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=800, messages=[{"role":"user","content":
    f"Review this crypto bot:\n- {len(trades)} trades | {len(wins)} wins | {wr:.1f}% WR | ${total:+.2f} PnL\n\nTrades:\n{trade_list}\n\nGive: 1. WHAT WORKED 2. WHAT HURT 3. TOP 3 FIXES 4. GRADE A/B/C/D. Be direct."}])

report = (f"📊 <b>Weekly Review — {datetime.now().strftime('%b %d')}</b>\n\n"
    f"Trades: {len(trades)} | WR: {wr:.1f}% | PnL: ${total:+.2f}\n\n"
    f"🧠 <b>Analysis:</b>\n{resp.content[0].text[:3500]}")
tg(report)
print("✅ Sent to Telegram!")
print(resp.content[0].text)