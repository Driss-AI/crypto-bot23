"""
Dashboard Server  Clean Version
Uses CoinGecko for prices (free, no account needed).
"""

import os
import json
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    USE_PG = True
else:
    USE_PG = False

app = Flask(__name__)

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

COINGECKO_IDS = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
    "SOL/USDT": "solana",
    "BNB/USDT": "binancecoin",
}


def get_conn():
    if USE_PG:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    import sqlite3
    return sqlite3.connect("memory/trades.db")


def get_prices():
    prices = {s: {"price": 0, "change": 0} for s in COINS}
    try:
        ids = ",".join(COINGECKO_IDS.values())
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBotDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for symbol, cg_id in COINGECKO_IDS.items():
            d = data.get(cg_id, {})
            prices[symbol] = {
                "price" : d.get("usd", 0) or 0,
                "change": d.get("usd_24h_change", 0) or 0,
            }
    except Exception as e:
        print(f"Price fetch error: {e}")
    return prices


def get_fear_greed():
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        return int(data["data"][0]["value"]), data["data"][0]["value_classification"]
    except:
        return 50, "Neutral"


def get_stats():
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='CLOSED'")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='CLOSED' AND pnl > 0")
        wins = c.fetchone()[0]
        c.execute("SELECT SUM(pnl) FROM paper_trades WHERE status='CLOSED'")
        total_pnl = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'")
        open_count = c.fetchone()[0]
        c.execute("SELECT action, entry_price, stop_loss, take_profit, size, timestamp FROM paper_trades WHERE status='OPEN' ORDER BY id DESC LIMIT 12")
        open_trades = c.fetchall()
        c.execute("SELECT action, entry_price, exit_price, pnl, exit_reason, timestamp FROM paper_trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 10")
        recent_closed = c.fetchall()
        try:
            c.execute("SELECT agent_name, score, total_calls FROM agent_credibility")
            creds = c.fetchall()
        except:
            creds = []
        try:
            c.execute("SELECT COUNT(*) FROM patterns")
            patterns = c.fetchone()[0]
        except:
            patterns = 0
        conn.close()
        win_rate = (wins / total * 100) if total > 0 else 0
        return {
            "total": total, "wins": wins, "losses": total - wins,
            "win_rate": round(win_rate, 1), "total_pnl": round(total_pnl, 2),
            "capital": round(1000 + total_pnl, 2), "open_count": open_count,
            "open_trades": open_trades, "recent_closed": recent_closed,
            "creds": creds, "patterns": patterns,
        }
    except Exception as e:
        print(f"Stats error: {e}")
        return {
            "total": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "capital": 1000, "open_count": 0,
            "open_trades": [], "recent_closed": [], "creds": [], "patterns": 0,
        }


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>DrissBot Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#080b0f;--surface:#0e1419;--border:#1a2332;--accent:#00ff88;--accent2:#ff3366;--accent3:#ffaa00;--text:#e0e8f0;--muted:#4a6080}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;padding:24px}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,255,136,.02) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,136,.02) 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}
.container{position:relative;z-index:1;max-width:1400px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid var(--border)}
.logo{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;letter-spacing:-1px}
.logo span{color:var(--accent)}
.live-badge{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--muted);letter-spacing:2px;text-transform:uppercase}
.live-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.stats-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:16px 20px}
.stat-label{font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.stat-value{font-family:'Syne',sans-serif;font-size:28px;font-weight:800;letter-spacing:-1px;line-height:1}
.green{color:var(--accent)}.red{color:var(--accent2)}.gold{color:var(--accent3)}
.price-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.price-card{background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:16px;position:relative;overflow:hidden}
.price-card::before{content:'';position:absolute;bottom:0;left:0;right:0;height:2px;background:var(--accent);opacity:.3}
.price-coin{font-size:10px;letter-spacing:3px;color:var(--muted);margin-bottom:8px}
.price-value{font-family:'Syne',sans-serif;font-size:22px;font-weight:700;margin-bottom:4px}
.price-change{font-size:11px}
.up{color:var(--accent)}.down{color:var(--accent2)}
.main-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.full-width{grid-column:1/-1}
.card{background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:20px}
.card-title{font-size:10px;letter-spacing:3px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);text-align:left;padding:8px 0;border-bottom:1px solid var(--border)}
td{padding:10px 0;border-bottom:1px solid rgba(26,35,50,.5);vertical-align:middle}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 8px;border-radius:2px;font-size:10px;letter-spacing:1px;font-weight:700}
.badge.buy{background:rgba(0,255,136,.15);color:var(--accent)}
.badge.sell{background:rgba(255,51,102,.15);color:var(--accent2)}
.badge.hold{background:rgba(255,170,0,.15);color:var(--accent3)}
.fg-bar{height:6px;background:var(--border);border-radius:3px;margin:12px 0 8px;overflow:hidden}
.fg-fill{height:100%;border-radius:3px}
.ef{background:linear-gradient(90deg,#ff3366,#ff6644)}.f{background:linear-gradient(90deg,#ff6644,#ffaa00)}
.n{background:linear-gradient(90deg,#ffaa00,#aaff00)}.g{background:linear-gradient(90deg,#aaff00,#00ff88)}
.eg{background:linear-gradient(90deg,#00ff88,#00ffcc)}
.cred-bar{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.cred-name{width:90px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}
.cred-track{flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden}
.cred-fill{height:100%;background:var(--accent);border-radius:2px}
.cred-score{font-size:11px;color:var(--accent);width:35px;text-align:right}
.empty{text-align:center;padding:30px;color:var(--muted);font-size:12px;letter-spacing:2px}
.ppos{color:var(--accent)}.pneg{color:var(--accent2)}
.ts{font-size:10px;color:var(--muted);text-align:right;margin-top:24px;letter-spacing:1px}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <div class="logo">DRISS<span>BOT</span> <span style="font-size:14px;color:var(--muted);font-weight:400">TRADING SYSTEM</span></div>
  <div class="live-badge"><div class="live-dot"></div>LIVE  AUTO-REFRESH 30S</div>
</div>
<div class="stats-grid">
  <div class="stat-card"><div class="stat-label">Capital</div><div class="stat-value {% if stats.total_pnl >= 0 %}green{% else %}red{% endif %}">${{ "{:,.0f}".format(stats.capital) }}</div></div>
  <div class="stat-card"><div class="stat-label">Total P&L</div><div class="stat-value {% if stats.total_pnl >= 0 %}green{% else %}red{% endif %}">{{ "+" if stats.total_pnl >= 0 else "" }}${{ "{:.2f}".format(stats.total_pnl) }}</div></div>
  <div class="stat-card"><div class="stat-label">Win Rate</div><div class="stat-value {% if stats.win_rate >= 50 %}green{% else %}red{% endif %}">{{ stats.win_rate }}%</div></div>
  <div class="stat-card"><div class="stat-label">Total Trades</div><div class="stat-value">{{ stats.total }}</div></div>
  <div class="stat-card"><div class="stat-label">Open Trades</div><div class="stat-value gold">{{ stats.open_count }}</div></div>
</div>
<div class="price-grid">
  {% for symbol, data in prices.items() %}
  <div class="price-card">
    <div class="price-coin">{{ symbol.replace('/USDT','') }} / USDT</div>
    <div class="price-value">{% if data.price %}${{ "{:,.2f}".format(data.price) }}{% else %}Loading...{% endif %}</div>
    <div class="price-change {% if data.change >= 0 %}up{% else %}down{% endif %}">{{ "" if data.change >= 0 else "" }} {{ "{:.2f}".format(data.change|abs) }}% 24h</div>
  </div>
  {% endfor %}
</div>
<div class="main-grid">
  <div class="card">
    <div class="card-title"> Open Trades</div>
    {% if stats.open_trades %}
    <table>
      <tr><th>Action</th><th>Entry</th><th>Stop</th><th>Target</th><th>Size</th><th>Time</th></tr>
      {% for t in stats.open_trades %}
      <tr>
        <td><span class="badge {{ t[0].lower() }}">{{ t[0] }}</span></td>
        <td>${{ "{:,.2f}".format(t[1]) }}</td>
        <td style="color:var(--accent2)">${{ "{:,.2f}".format(t[2]) }}</td>
        <td style="color:var(--accent)">${{ "{:,.2f}".format(t[3]) }}</td>
        <td>${{ "{:.0f}".format(t[4]) }}</td>
        <td style="color:var(--muted);font-size:10px">{{ t[5][:10] if t[5] else "" }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}<div class="empty">NO OPEN TRADES</div>{% endif %}
  </div>
  <div style="display:flex;flex-direction:column;gap:12px">
    <div class="card">
      <div class="card-title"> Fear & Greed Index</div>
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <div style="font-family:'Syne',sans-serif;font-size:42px;font-weight:800">{{ fg_value }}</div>
        <div style="font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:2px">{{ fg_label }}</div>
      </div>
      <div class="fg-bar"><div class="fg-fill {% if fg_value<=25 %}ef{% elif fg_value<=45 %}f{% elif fg_value<=55 %}n{% elif fg_value<=75 %}g{% else %}eg{% endif %}" style="width:{{ fg_value }}%"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--muted);letter-spacing:1px"><span>EXTREME FEAR</span><span>NEUTRAL</span><span>EXTREME GREED</span></div>
    </div>
    <div class="card">
      <div class="card-title"> Agent Credibility</div>
      {% if stats.creds %}
        {% for cred in stats.creds %}
        <div class="cred-bar">
          <div class="cred-name">{{ cred[0] }}</div>
          <div class="cred-track"><div class="cred-fill" style="width:{{ (cred[1]*100)|int }}%"></div></div>
          <div class="cred-score">{{ "{:.2f}".format(cred[1]) }}</div>
          <div style="font-size:10px;color:var(--muted);width:50px">{{ cred[2] }} calls</div>
        </div>
        {% endfor %}
      {% else %}<div class="empty" style="padding:16px">LEARNING... (need more trades)</div>{% endif %}
      <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);font-size:11px;color:var(--muted)">Patterns discovered: <span style="color:var(--accent)">{{ stats.patterns }}</span></div>
    </div>
  </div>
  <div class="card full-width">
    <div class="card-title"> Recent Closed Trades</div>
    {% if stats.recent_closed %}
    <table>
      <tr><th>Action</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Result</th><th>Date</th></tr>
      {% for t in stats.recent_closed %}
      <tr>
        <td><span class="badge {{ t[0].lower() }}">{{ t[0] }}</span></td>
        <td>${{ "{:,.2f}".format(t[1]) }}</td>
        <td>${{ "{:,.2f}".format(t[2]) if t[2] else "" }}</td>
        <td class="{% if t[3] and t[3]>=0 %}ppos{% else %}pneg{% endif %}">{{ "+" if t[3] and t[3]>=0 else "" }}${{ "{:.2f}".format(t[3]) if t[3] else "" }}</td>
        <td style="font-size:11px">{{ t[4] or "" }}</td>
        <td style="color:var(--muted);font-size:10px">{{ t[5][:10] if t[5] else "" }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}<div class="empty">NO CLOSED TRADES YET</div>{% endif %}
  </div>
</div>
<div class="ts">LAST UPDATED: {{ now }}  DRISSBOT MULTI-AGENT SYSTEM</div>
</div>
</body>
</html>"""


@app.route("/")
def dashboard():
    fg_value, fg_label = get_fear_greed()
    return render_template_string(
        HTML,
        stats    = get_stats(),
        prices   = get_prices(),
        fg_value = fg_value,
        fg_label = fg_label,
        now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
