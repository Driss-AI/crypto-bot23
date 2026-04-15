"""
WEEKLY PERFORMANCE REVIEW
Run: python3 weekly_review.py
"""
import os, psycopg2, anthropic, requests
from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHAT   = os.getenv("TELEGRAM_CHAT_ID")

def tg(msg):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT, "text": msg, "parse_mode": "HTML"}, timeout=15)

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur  = conn.cursor()
cur.execute("""
    SELECT action, symbol, entry_price, exit_price, pnl, confidence, style, created_at
    FROM trades WHERE status='closed' AND created_at >= NOW() - INTERVAL '7 days'
    ORDER BY created_at DESC
""")
trades = cur.fetchall()
cur.execute("SELECT pattern_key, occurrences, win_rate, avg_pnl FROM patterns ORDER BY occurrences DESC LIMIT 10")
patterns = cur.fetchall()
conn.close()

if not trades:
    tg("📊 <b>Weekly Review</b>\n\nNo closed trades this week yet.")
    print("No trades this week.")
    exit()

wins  = [t for t in trades if t[4] and t[4] > 0]
total = sum(t[4] for t in trades if t[4])
wr    = len(wins)/len(trades)*100

style_lines = ""
for s in ["scalp","day","swing"]:
    pnls = [t[4] or 0 for t in trades if t[6]==s]
    if pnls:
        e = {"scalp":"🔥","day":"📈","swing":"🌊"}[s]
        style_lines += f"{e} {s.upper()}: {len(pnls)} trades | ${sum(pnls):+.2f}\n"

trade_list = "\n".join([
    f"{'✅' if t[4]>0 else '❌'} {t[1]} {t[0]} ${t[4]:.2f} ({t[5]})"
    for t in trades[:20]
])
pat_list = "\n".join([f"• {p[0]}: {p[1]}x WR:{float(p[2]):.0%} avg:${float(p[3]):.2f}" for p in patterns]) or "None yet"

resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=800, messages=[{"role":"user","content":f"""
Review this crypto bot's week:
- {len(trades)} trades | {len(wins)} wins | {wr:.1f}% WR | ${total:+.2f} PnL
Styles: {style_lines}
Trades: {trade_list}
Patterns: {pat_list}

Give:
1. WHAT WORKED
2. WHAT HURT  
3. TOP 3 FIXES for next week
4. GRADE (A/B/C/D)
Be specific and direct.
"""}])

report = (f"📊 <b>Weekly Review — {datetime.now().strftime('%b %d')}</b>\n\n"
    f"Trades: {len(trades)} | WR: {wr:.1f}% | PnL: ${total:+.2f}\n{style_lines}\n"
    f"🧠 <b>Analysis:</b>\n{resp.content[0].text[:3500]}")
tg(report)
print("✅ Sent to Telegram!")
print(resp.content[0].text)
