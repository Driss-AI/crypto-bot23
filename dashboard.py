"""
DrissBot Dashboard — Neural Trading Terminal
2026 aesthetic: Bloomberg × Blade Runner × Quant HUD
"""

import os, json, urllib.request
from datetime import datetime
from flask import Flask, jsonify, render_template_string
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    import psycopg2
    USE_PG = True
else:
    USE_PG = False

app = Flask(__name__)

COINS = ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT"]
COINGECKO_IDS = {"BTC/USDT":"bitcoin","ETH/USDT":"ethereum","SOL/USDT":"solana","BNB/USDT":"binancecoin"}
_fg_cache = {"value":50,"label":"Neutral","updated":""}

def get_conn():
    if USE_PG: return psycopg2.connect(DATABASE_URL, sslmode="require")
    import sqlite3; return sqlite3.connect("memory/trades.db")

def get_prices():
    prices = {s:{"price":0,"change":0} for s in COINS}
    try:
        ids = ",".join(COINGECKO_IDS.values())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent":"DrissBot/2.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for sym, cg in COINGECKO_IDS.items():
            d = data.get(cg,{})
            prices[sym] = {"price":d.get("usd",0) or 0,"change":d.get("usd_24h_change",0) or 0}
    except Exception as e: print(f"Price err: {e}")
    return prices

def get_fear_greed():
    global _fg_cache
    today = datetime.now().strftime("%Y-%m-%d")
    if _fg_cache["updated"] == today: return _fg_cache["value"], _fg_cache["label"], _fg_cache["updated"]
    try:
        req = urllib.request.Request("https://api.alternative.me/fng/?limit=1", headers={"User-Agent":"CryptoBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        val = int(data["data"][0]["value"]); label = data["data"][0]["value_classification"]
        _fg_cache = {"value":val,"label":label,"updated":today}
    except: pass
    return _fg_cache["value"], _fg_cache["label"], _fg_cache["updated"]

def get_stats():
    try:
        conn = get_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='CLOSED'"); total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='CLOSED' AND pnl > 0"); wins = c.fetchone()[0]
        c.execute("SELECT SUM(pnl) FROM paper_trades WHERE status='CLOSED'"); total_pnl = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'"); open_count = c.fetchone()[0]
        try:
            c.execute("SELECT action,entry_price,stop_loss,take_profit,size,timestamp,symbol,style,score FROM paper_trades WHERE status='OPEN' ORDER BY id DESC LIMIT 8")
            open_trades = c.fetchall()
        except:
            c.execute("SELECT action,entry_price,stop_loss,take_profit,size,timestamp FROM paper_trades WHERE status='OPEN' ORDER BY id DESC LIMIT 8")
            open_trades = [r+('?','?',0) for r in c.fetchall()]
        try:
            c.execute("SELECT action,entry_price,exit_price,pnl,exit_reason,timestamp,symbol,style,score FROM paper_trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 8")
            recent_closed = c.fetchall()
        except:
            c.execute("SELECT action,entry_price,exit_price,pnl,exit_reason,timestamp FROM paper_trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 8")
            recent_closed = [r+('?','?',0) for r in c.fetchall()]
        try:
            c.execute("SELECT style,COUNT(*) as t,SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as w,COALESCE(SUM(pnl),0) as p FROM paper_trades WHERE status='CLOSED' AND style IS NOT NULL GROUP BY style")
            style_stats = {row[0]:{"total":row[1],"wins":row[2],"pnl":row[3]} for row in c.fetchall()}
        except: style_stats = {}
        conn.close()
        win_rate = (wins/total*100) if total > 0 else 0
        return {"total":total,"wins":wins,"losses":total-wins,"win_rate":round(win_rate,1),"total_pnl":round(total_pnl,2),"capital":round(1000+total_pnl,2),"open_count":open_count,"open_trades":open_trades,"recent_closed":recent_closed,"style_stats":style_stats}
    except Exception as e:
        print(f"Stats err: {e}")
        return {"total":0,"wins":0,"losses":0,"win_rate":0,"total_pnl":0,"capital":1000,"open_count":0,"open_trades":[],"recent_closed":[],"style_stats":{}}

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>DRISSBOT // NEURAL TRADING TERMINAL</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Bebas+Neue&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
:root{
  --void:#020408;
  --deep:#060d16;
  --panel:#08111e;
  --border:#0a2540;
  --border2:#0d3060;
  --cyan:#00d4ff;
  --cyan2:#00aacc;
  --green:#00ff9d;
  --orange:#ff6b00;
  --gold:#ffd700;
  --red:#ff2244;
  --muted:#1a4060;
  --text:#8ab8d8;
  --bright:#c8e8ff;
}
*{margin:0;padding:0;box-sizing:border-box}
html{background:var(--void)}
body{
  background:var(--void);
  color:var(--text);
  font-family:'JetBrains Mono',monospace;
  min-height:100vh;
  overflow-x:hidden;
  position:relative;
}

/* Scanline overlay */
body::after{
  content:'';
  position:fixed;
  inset:0;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,212,255,.015) 2px,rgba(0,212,255,.015) 4px);
  pointer-events:none;
  z-index:9999;
}

canvas#bg{position:fixed;inset:0;z-index:0;opacity:.4}

.wrap{position:relative;z-index:1;padding:20px 24px;max-width:1600px;margin:0 auto}

/* ── HEADER ── */
.header{
  display:flex;justify-content:space-between;align-items:center;
  padding:12px 0 20px;
  border-bottom:1px solid var(--border2);
  margin-bottom:20px;
}
.logo-block{display:flex;align-items:baseline;gap:16px}
.logo{
  font-family:'Orbitron',monospace;
  font-size:26px;font-weight:900;
  letter-spacing:4px;
  color:var(--cyan);
  text-shadow:0 0 20px rgba(0,212,255,.6),0 0 60px rgba(0,212,255,.2);
  animation:glitch 8s infinite;
}
@keyframes glitch{
  0%,95%,100%{text-shadow:0 0 20px rgba(0,212,255,.6),0 0 60px rgba(0,212,255,.2)}
  96%{text-shadow:-2px 0 var(--orange),2px 0 var(--cyan),0 0 20px rgba(0,212,255,.6)}
  97%{text-shadow:2px 0 var(--red),-2px 0 var(--green),0 0 20px rgba(0,212,255,.6)}
  98%{text-shadow:-1px 0 var(--cyan),1px 0 var(--orange),0 0 20px rgba(0,212,255,.6)}
}
.logo-sub{font-size:9px;letter-spacing:5px;color:var(--muted);text-transform:uppercase}
.header-right{display:flex;align-items:center;gap:24px}
.status-pill{
  display:flex;align-items:center;gap:8px;
  font-size:10px;letter-spacing:3px;color:var(--cyan2);
  text-transform:uppercase;
}
.pulse-dot{
  width:7px;height:7px;border-radius:50%;
  background:var(--green);
  box-shadow:0 0 8px var(--green);
  animation:radar 1.5s ease-out infinite;
}
@keyframes radar{
  0%{box-shadow:0 0 0 0 rgba(0,255,157,.6),0 0 8px var(--green)}
  70%{box-shadow:0 0 0 10px rgba(0,255,157,0),0 0 8px var(--green)}
  100%{box-shadow:0 0 0 0 rgba(0,255,157,0),0 0 8px var(--green)}
}
.clock-block{text-align:right}
.clock{font-family:'Orbitron',monospace;font-size:18px;font-weight:700;color:var(--bright);letter-spacing:3px}
.clock-date{font-size:9px;letter-spacing:2px;color:var(--muted)}

/* ── TICKER TAPE ── */
.ticker-wrap{
  overflow:hidden;border:1px solid var(--border);
  background:var(--panel);margin-bottom:20px;
  height:32px;display:flex;align-items:center;
  position:relative;
}
.ticker-wrap::before,.ticker-wrap::after{
  content:'';position:absolute;top:0;bottom:0;width:40px;z-index:2;
}
.ticker-wrap::before{left:0;background:linear-gradient(90deg,var(--panel),transparent)}
.ticker-wrap::after{right:0;background:linear-gradient(-90deg,var(--panel),transparent)}
.ticker{
  display:flex;gap:0;white-space:nowrap;
  animation:scroll 30s linear infinite;
}
@keyframes scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.tick-item{
  display:inline-flex;align-items:center;gap:8px;
  padding:0 28px;font-size:11px;letter-spacing:1px;
  border-right:1px solid var(--border);
}
.tick-sym{color:var(--bright);font-weight:700}
.tick-up{color:var(--green)}.tick-dn{color:var(--red)}

/* ── REFRESH PROGRESS ── */
.refbar{height:2px;background:var(--border);margin-bottom:20px;overflow:hidden}
.refill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--green));animation:refill 5s linear infinite;box-shadow:0 0 6px var(--cyan)}
@keyframes refill{from{width:100%;opacity:1}to{width:0%;opacity:.3}}

/* ── KPI STRIP ── */
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px}
.kpi{
  background:var(--panel);
  border:1px solid var(--border);
  padding:14px 18px;
  position:relative;overflow:hidden;
  transition:border-color .3s;
}
.kpi::before,.kpi::after{
  content:'';position:absolute;
  width:8px;height:8px;
  border-color:var(--cyan2);border-style:solid;
}
.kpi::before{top:4px;left:4px;border-width:1px 0 0 1px}
.kpi::after{bottom:4px;right:4px;border-width:0 1px 1px 0}
.kpi:hover{border-color:var(--cyan2)}
.kpi-label{font-size:8px;letter-spacing:4px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.kpi-val{font-family:'Orbitron',monospace;font-size:24px;font-weight:700;letter-spacing:1px;line-height:1;transition:all .3s}
.kpi-val.pos{color:var(--green);text-shadow:0 0 20px rgba(0,255,157,.4)}
.kpi-val.neg{color:var(--red);text-shadow:0 0 20px rgba(255,34,68,.4)}
.kpi-val.neu{color:var(--cyan);text-shadow:0 0 20px rgba(0,212,255,.4)}
.kpi-val.gold{color:var(--gold);text-shadow:0 0 20px rgba(255,215,0,.4)}

/* ── PRICE GRID ── */
.price-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
.price-card{
  background:var(--panel);border:1px solid var(--border);
  padding:14px 16px;position:relative;overflow:hidden;
  cursor:default;transition:border-color .3s;
}
.price-card:hover{border-color:var(--cyan2)}
.price-card::after{
  content:'';position:absolute;bottom:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--cyan2),transparent);
  opacity:.5;
}
.pc-sym{font-size:9px;letter-spacing:4px;color:var(--muted);margin-bottom:6px}
.pc-price{font-family:'Orbitron',monospace;font-size:19px;font-weight:700;color:var(--bright);transition:color .4s;margin-bottom:3px}
.pc-price.up{color:var(--green);text-shadow:0 0 10px rgba(0,255,157,.5)}
.pc-price.dn{color:var(--red);text-shadow:0 0 10px rgba(255,34,68,.5)}
.pc-chg{font-size:10px;letter-spacing:1px}
.pc-chg.pos{color:var(--green)}.pc-chg.neg{color:var(--red)}
.pc-bar{height:2px;background:var(--border);margin-top:8px;border-radius:1px;overflow:hidden}
.pc-bar-fill{height:100%;border-radius:1px;transition:width .6s}

/* ── MAIN GRID ── */
.main{display:grid;grid-template-columns:1.2fr .8fr;gap:12px;margin-bottom:12px}
.card{
  background:var(--panel);border:1px solid var(--border);
  padding:18px;position:relative;
  transition:border-color .3s;
}
.card:hover{border-color:var(--border2)}
/* HUD corner brackets */
.card::before,.card::after{
  content:'';position:absolute;
  width:12px;height:12px;
  border-color:var(--cyan2);border-style:solid;
  opacity:.5;
}
.card::before{top:0;left:0;border-width:1px 0 0 1px}
.card::after{bottom:0;right:0;border-width:0 1px 1px 0}
.card-hdr{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:14px;
}
.card-title{
  font-size:8px;letter-spacing:5px;text-transform:uppercase;
  color:var(--muted);display:flex;align-items:center;gap:8px;
}
.card-title::before{content:'//';color:var(--cyan2);font-weight:700}
.card-ct{font-size:10px;color:var(--cyan);letter-spacing:1px}
.full{grid-column:1/-1}

/* ── TABLES ── */
table{width:100%;border-collapse:collapse;font-size:11px}
th{
  font-size:8px;letter-spacing:3px;text-transform:uppercase;
  color:var(--muted);text-align:left;padding:0 0 10px;
  border-bottom:1px solid var(--border);
}
td{padding:9px 0;border-bottom:1px solid rgba(10,37,64,.6);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(0,212,255,.02)}
.badge{
  display:inline-flex;align-items:center;justify-content:center;
  padding:2px 8px;font-size:9px;letter-spacing:2px;font-weight:700;
  font-family:'Orbitron',monospace;
}
.badge.buy{background:rgba(0,255,157,.1);color:var(--green);border:1px solid rgba(0,255,157,.3)}
.badge.sell{background:rgba(255,34,68,.1);color:var(--red);border:1px solid rgba(255,34,68,.3)}
.stag{
  font-size:9px;letter-spacing:1px;color:var(--muted);
  padding:2px 7px;border:1px solid var(--border);
}
.ppos{color:var(--green)}.pneg{color:var(--red)}

/* ── RIGHT COLUMN ── */
.right-col{display:flex;flex-direction:column;gap:12px}

/* Fear & Greed */
.fg-num{
  font-family:'Orbitron',monospace;font-size:52px;font-weight:900;
  line-height:1;transition:all .5s;
}
.fg-label{font-size:9px;letter-spacing:5px;text-transform:uppercase;color:var(--muted);margin-top:4px}
.fg-bar{height:4px;background:var(--border);margin:14px 0 8px;position:relative;overflow:visible}
.fg-fill{height:100%;transition:width .8s cubic-bezier(.4,0,.2,1);position:relative}
.fg-fill::after{
  content:'';position:absolute;right:-1px;top:-4px;
  width:2px;height:12px;
  background:white;box-shadow:0 0 6px white;
}
.fg-labels{display:flex;justify-content:space-between;font-size:8px;letter-spacing:1px;color:var(--muted)}
.fg-date{font-size:9px;color:var(--muted);margin-top:8px;letter-spacing:1px}

/* Signal bars */
.sig-row{display:flex;align-items:center;gap:10px;margin-bottom:11px}
.sig-lbl{width:84px;font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
.sig-track{flex:1;height:3px;background:var(--border);position:relative;overflow:hidden}
.sig-fill{height:100%;transition:width .6s}
.sig-pct{font-size:10px;font-weight:700;width:36px;text-align:right;font-family:'Orbitron',monospace}
.sig-note{font-size:9px;color:var(--muted);width:52px;text-align:right}

/* Style breakdown */
.style-row{
  display:flex;align-items:center;gap:10px;padding:8px 0;
  border-bottom:1px solid rgba(10,37,64,.8);
}
.style-row:last-child{border:none}
.style-emo{font-size:13px}
.style-name{font-size:10px;font-family:'Orbitron',monospace;color:var(--bright);width:50px}
.style-wr{
  font-size:10px;font-family:'Orbitron',monospace;
  padding:2px 6px;border:1px solid var(--border);
}

/* Footer */
.footer{
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 0 0;
  border-top:1px solid var(--border);
  margin-top:8px;font-size:9px;letter-spacing:2px;color:var(--muted);
}
.footer-id{color:var(--cyan2)}

/* EMPTY */
.empty{text-align:center;padding:28px;color:var(--muted);font-size:10px;letter-spacing:3px}

</style>
</head>
<body>
<canvas id="bg"></canvas>
<div class="wrap">

  <!-- HEADER -->
  <div class="header">
    <div class="logo-block">
      <div class="logo">DRISSBOT</div>
      <div class="logo-sub">Neural Trading Terminal v2.0</div>
    </div>
    <div class="header-right">
      <div class="status-pill"><div class="pulse-dot"></div>LIVE · 5S SYNC</div>
      <div class="clock-block">
        <div class="clock" id="clock">--:--:--</div>
        <div class="clock-date" id="cdate">----·--·--</div>
      </div>
    </div>
  </div>

  <!-- TICKER -->
  <div class="ticker-wrap">
    <div class="ticker" id="ticker">
      <span class="tick-item"><span class="tick-sym">BTC</span><span id="tk-BTC" class="tick-up">--</span></span>
      <span class="tick-item"><span class="tick-sym">ETH</span><span id="tk-ETH" class="tick-up">--</span></span>
      <span class="tick-item"><span class="tick-sym">SOL</span><span id="tk-SOL" class="tick-up">--</span></span>
      <span class="tick-item"><span class="tick-sym">BNB</span><span id="tk-BNB" class="tick-up">--</span></span>
      <span class="tick-item" style="color:var(--muted)">F&amp;G INDEX <span id="tk-fg" style="color:var(--gold)">--</span></span>
      <span class="tick-item"><span class="tick-sym">BTC</span><span id="tk-BTC2" class="tick-up">--</span></span>
      <span class="tick-item"><span class="tick-sym">ETH</span><span id="tk-ETH2" class="tick-up">--</span></span>
      <span class="tick-item"><span class="tick-sym">SOL</span><span id="tk-SOL2" class="tick-up">--</span></span>
      <span class="tick-item"><span class="tick-sym">BNB</span><span id="tk-BNB2" class="tick-up">--</span></span>
      <span class="tick-item" style="color:var(--muted)">F&amp;G INDEX <span id="tk-fg2" style="color:var(--gold)">--</span></span>
    </div>
  </div>

  <!-- REFRESH BAR -->
  <div class="refbar"><div class="refill"></div></div>

  <!-- KPI STRIP -->
  <div class="kpi-grid">
    <div class="kpi"><div class="kpi-label">Capital</div><div class="kpi-val neu" id="capital">$0</div></div>
    <div class="kpi"><div class="kpi-label">Total P&amp;L</div><div class="kpi-val" id="pnl">$0</div></div>
    <div class="kpi"><div class="kpi-label">Win Rate</div><div class="kpi-val" id="winrate">0%</div></div>
    <div class="kpi"><div class="kpi-label">Closed Trades</div><div class="kpi-val neu" id="total">0</div></div>
    <div class="kpi"><div class="kpi-label">Open Trades</div><div class="kpi-val gold" id="open-count">0</div></div>
  </div>

  <!-- PRICE GRID -->
  <div class="price-grid">
    <div class="price-card"><div class="pc-sym">BTC / USDT</div><div class="pc-price" id="p-BTC">--</div><div class="pc-chg" id="c-BTC">--</div><div class="pc-bar"><div class="pc-bar-fill" id="b-BTC" style="width:50%;background:var(--cyan)"></div></div></div>
    <div class="price-card"><div class="pc-sym">ETH / USDT</div><div class="pc-price" id="p-ETH">--</div><div class="pc-chg" id="c-ETH">--</div><div class="pc-bar"><div class="pc-bar-fill" id="b-ETH" style="width:50%;background:var(--cyan)"></div></div></div>
    <div class="price-card"><div class="pc-sym">SOL / USDT</div><div class="pc-price" id="p-SOL">--</div><div class="pc-chg" id="c-SOL">--</div><div class="pc-bar"><div class="pc-bar-fill" id="b-SOL" style="width:50%;background:var(--cyan)"></div></div></div>
    <div class="price-card"><div class="pc-sym">BNB / USDT</div><div class="pc-price" id="p-BNB">--</div><div class="pc-chg" id="c-BNB">--</div><div class="pc-bar"><div class="pc-bar-fill" id="b-BNB" style="width:50%;background:var(--cyan)"></div></div></div>
  </div>

  <!-- MAIN GRID -->
  <div class="main">

    <!-- LEFT: TRADES -->
    <div style="display:flex;flex-direction:column;gap:12px">

      <!-- Open Trades -->
      <div class="card">
        <div class="card-hdr">
          <div class="card-title">Open Positions</div>
          <div class="card-ct" id="open-ct">0 ACTIVE</div>
        </div>
        <div id="open-body"><div class="empty">NO ACTIVE POSITIONS</div></div>
      </div>

      <!-- Closed Trades -->
      <div class="card">
        <div class="card-hdr">
          <div class="card-title">Execution Log</div>
          <div class="card-ct">LAST 8</div>
        </div>
        <div id="closed-body"><div class="empty">NO RECORDS</div></div>
      </div>

    </div>

    <!-- RIGHT COLUMN -->
    <div class="right-col">

      <!-- Fear & Greed -->
      <div class="card">
        <div class="card-hdr">
          <div class="card-title">Market Sentiment</div>
          <div class="card-ct" id="fg-lbl">--</div>
        </div>
        <div style="display:flex;align-items:flex-end;gap:16px">
          <div class="fg-num" id="fg-num">--</div>
          <div style="margin-bottom:8px">
            <div class="fg-label">FEAR &amp; GREED</div>
          </div>
        </div>
        <div class="fg-bar"><div class="fg-fill" id="fg-fill" style="width:50%"></div></div>
        <div class="fg-labels"><span>EXTREME FEAR</span><span>NEUTRAL</span><span>EXTREME GREED</span></div>
        <div class="fg-date" id="fg-date">Loading...</div>
      </div>

      <!-- Signal Weights -->
      <div class="card">
        <div class="card-hdr">
          <div class="card-title">Signal Weights</div>
          <div class="card-ct" id="wgt-mode">STATIC</div>
        </div>
        <div id="sig-bars">
          <div class="sig-row"><div class="sig-lbl">Technical</div><div class="sig-track"><div class="sig-fill" style="width:45%;background:var(--cyan)"></div></div><div class="sig-pct" style="color:var(--cyan)">45%</div><div class="sig-note">regime</div></div>
          <div class="sig-row"><div class="sig-lbl">Macro</div><div class="sig-track"><div class="sig-fill" style="width:20%;background:var(--gold)"></div></div><div class="sig-pct" style="color:var(--gold)">20%</div><div class="sig-note">regime</div></div>
          <div class="sig-row"><div class="sig-lbl">Sentiment</div><div class="sig-track"><div class="sig-fill" style="width:20%;background:#00aaff"></div></div><div class="sig-pct" style="color:#00aaff">20%</div><div class="sig-note">regime</div></div>
          <div class="sig-row"><div class="sig-lbl">Whale</div><div class="sig-track"><div class="sig-fill" style="width:15%;background:#aa88ff"></div></div><div class="sig-pct" style="color:#aa88ff">15%</div><div class="sig-note">regime</div></div>
        </div>
        <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);font-size:9px;color:var(--muted);letter-spacing:1px" id="wgt-note">Dynamic weights activate after 30 closed trades</div>
      </div>

      <!-- Style Breakdown -->
      <div class="card">
        <div class="card-hdr">
          <div class="card-title">Style Performance</div>
        </div>
        <div id="style-breakdown"><div class="empty" style="padding:12px">AWAITING DATA</div></div>
      </div>

    </div>
  </div>

  <!-- FOOTER -->
  <div class="footer">
    <div><span class="footer-id">DRISSBOT // </span>MULTI-AGENT TRADING SYSTEM // PAPER MODE</div>
    <div id="last-upd">SYNC: --:--:--</div>
  </div>

</div>

<script>
// ── Canvas particle grid ──────────────────────────────────────────────────────
(function(){
  const c = document.getElementById('bg');
  const ctx = c.getContext('2d');
  const resize = () => { c.width = window.innerWidth; c.height = window.innerHeight; };
  resize(); window.addEventListener('resize', resize);
  const pts = Array.from({length:80},()=>({
    x: Math.random()*window.innerWidth,
    y: Math.random()*window.innerHeight,
    vx:(Math.random()-.5)*.3, vy:(Math.random()-.5)*.3,
    r: Math.random()*1.5+.5
  }));
  function frame(){
    ctx.clearRect(0,0,c.width,c.height);
    pts.forEach(p=>{
      p.x+=p.vx; p.y+=p.vy;
      if(p.x<0)p.x=c.width; if(p.x>c.width)p.x=0;
      if(p.y<0)p.y=c.height; if(p.y>c.height)p.y=0;
      ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle='rgba(0,212,255,.5)'; ctx.fill();
    });
    pts.forEach((a,i)=>pts.slice(i+1).forEach(b=>{
      const d=Math.hypot(a.x-b.x,a.y-b.y);
      if(d<120){
        ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
        ctx.strokeStyle=`rgba(0,212,255,${.15*(1-d/120)})`; ctx.lineWidth=.5; ctx.stroke();
      }
    }));
    requestAnimationFrame(frame);
  }
  frame();
})();

// ── Clock ──────────────────────────────────────────────────────────────────────
function tickClock(){
  const now = new Date();
  document.getElementById('clock').textContent = now.toLocaleTimeString('en-GB',{hour12:false});
  document.getElementById('cdate').textContent = now.toISOString().slice(0,10).replace(/-/g,'·');
}
setInterval(tickClock,1000); tickClock();

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmt=(n,d=2)=>Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmts=(n,d=2)=>(n>=0?'+':'')+fmt(n,d);
const COINS=['BTC','ETH','SOL','BNB'];
let prevP={};

function fgGradient(v){
  if(v<=25)return 'linear-gradient(90deg,#ff2244,#ff6644)';
  if(v<=45)return 'linear-gradient(90deg,#ff6644,#ffd700)';
  if(v<=55)return 'linear-gradient(90deg,#ffd700,#aaff00)';
  if(v<=75)return 'linear-gradient(90deg,#aaff00,#00ff9d)';
  return 'linear-gradient(90deg,#00ff9d,#00d4ff)';
}
function fgColor(v){
  if(v<=25)return '#ff2244';
  if(v<=45)return '#ff6644';
  if(v<=55)return '#ffd700';
  if(v<=75)return '#00ff9d';
  return '#00d4ff';
}

// ── Fetch & render ─────────────────────────────────────────────────────────────
async function tick(){
  try{
    const res = await fetch('/api/data');
    const d = await res.json();
    const s = d.stats;

    // KPIs
    const pnl = s.total_pnl;
    document.getElementById('capital').textContent = '$'+fmt(s.capital,0);
    const pnlEl = document.getElementById('pnl');
    pnlEl.textContent = (pnl>=0?'+':'')+' $'+fmt(pnl);
    pnlEl.className = 'kpi-val '+(pnl>=0?'pos':'neg');
    const wrEl = document.getElementById('winrate');
    wrEl.textContent = s.win_rate+'%';
    wrEl.className = 'kpi-val '+(s.win_rate>=50?'pos':'neg');
    document.getElementById('total').textContent = s.total;
    document.getElementById('open-count').textContent = s.open_count;

    // Prices
    COINS.forEach(coin=>{
      const key=coin+'/USDT', dt=d.prices[key];
      if(!dt) return;
      const prEl=document.getElementById('p-'+coin);
      const prev=prevP[coin]||0;
      const np=dt.price;
      if(prev && prev!==np){
        prEl.className='pc-price '+(np>prev?'up':'dn');
        setTimeout(()=>prEl.className='pc-price',1200);
      }
      prEl.textContent='$'+fmt(np);
      prevP[coin]=np;
      const chg=dt.change;
      const cEl=document.getElementById('c-'+coin);
      cEl.textContent=(chg>=0?'▲ ':'▼ ')+fmt(Math.abs(chg))+'%';
      cEl.className='pc-chg '+(chg>=0?'pos':'neg');
      // bar shows % change mapped to 0-100
      const bPct=Math.min(100,Math.max(0,50+chg*3));
      const bEl=document.getElementById('b-'+coin);
      bEl.style.width=bPct+'%';
      bEl.style.background=chg>=0?'var(--green)':'var(--red)';
      // ticker
      ['','2'].forEach(sfx=>{
        const tel=document.getElementById('tk-'+coin+sfx);
        if(tel){tel.textContent='$'+fmt(np,0)+' '+(chg>=0?'▲':'▼')+fmt(Math.abs(chg),1)+'%';tel.className=chg>=0?'tick-up':'tick-dn';}
      });
    });

    // F&G
    const fv=d.fg_value;
    document.getElementById('fg-num').textContent=fv;
    document.getElementById('fg-num').style.color=fgColor(fv);
    document.getElementById('fg-num').style.textShadow=`0 0 30px ${fgColor(fv)}88`;
    document.getElementById('fg-lbl').textContent=d.fg_label.toUpperCase();
    const ff=document.getElementById('fg-fill');
    ff.style.width=fv+'%'; ff.style.background=fgGradient(fv);
    ff.style.boxShadow=`0 0 8px ${fgColor(fv)}`;
    document.getElementById('fg-date').textContent=d.fg_date?'Updated: '+d.fg_date+' (daily index)':'Updates once per day';
    ['','2'].forEach(s=>{const el=document.getElementById('tk-fg'+s);if(el)el.textContent=fv+' '+d.fg_label.toUpperCase();});

    // Open trades
    const ob=document.getElementById('open-body');
    const oct=document.getElementById('open-ct');
    oct.textContent=s.open_count+' ACTIVE';
    if(s.open_trades && s.open_trades.length>0){
      let h='<table><tr><th>Side</th><th>Style</th><th>Entry</th><th>SL</th><th>TP</th><th>Score</th><th>Size</th></tr>';
      s.open_trades.forEach(t=>{
        const [action,entry,sl,tp,size,ts,sym,style,score]=t;
        const coin=(sym||'?').replace('/USDT','');
        const sc=score?(score>0?'+':'')+Number(score).toFixed(3):'--';
        const scCol=score>0?'var(--green)':score<0?'var(--red)':'var(--muted)';
        h+=`<tr>
          <td><span class="badge ${action.toLowerCase()}">${action}</span></td>
          <td><span class="stag">${(style||'?').toUpperCase()} ${coin}</span></td>
          <td style="color:var(--bright)">$${fmt(entry)}</td>
          <td style="color:var(--red)">$${fmt(sl)}</td>
          <td style="color:var(--green)">$${fmt(tp)}</td>
          <td style="color:${scCol};font-family:'Orbitron',monospace;font-size:10px">${sc}</td>
          <td style="color:var(--muted)">$${fmt(size,0)}</td>
        </tr>`;
      });
      ob.innerHTML=h+'</table>';
    } else { ob.innerHTML='<div class="empty">NO ACTIVE POSITIONS</div>'; }

    // Closed trades
    const cb=document.getElementById('closed-body');
    if(s.recent_closed && s.recent_closed.length>0){
      let h='<table><tr><th>Side</th><th>Style</th><th>Entry</th><th>Exit</th><th>P&amp;L</th><th>Score</th><th>Result</th><th>Date</th></tr>';
      s.recent_closed.forEach(t=>{
        const [action,entry,exit_p,pnl,reason,ts,sym,style,score]=t;
        const coin=(sym||'?').replace('/USDT','');
        const ppos=pnl>=0?'ppos':'pneg';
        const pstr=(pnl>=0?'+':'')+' $'+fmt(pnl);
        const sc=score?(score>0?'+':'')+Number(score).toFixed(3):'--';
        const scCol=score>0?'var(--green)':score<0?'var(--red)':'var(--muted)';
        const rColor=reason&&reason.includes('Take')?' style="color:var(--green)"':reason&&reason.includes('Stop')?' style="color:var(--red)"':'';
        h+=`<tr>
          <td><span class="badge ${action.toLowerCase()}">${action}</span></td>
          <td><span class="stag">${(style||'?').toUpperCase()} ${coin}</span></td>
          <td style="color:var(--bright)">$${fmt(entry)}</td>
          <td>${exit_p?'$'+fmt(exit_p):'--'}</td>
          <td class="${ppos}" style="font-family:'Orbitron',monospace;font-size:10px">${pstr}</td>
          <td style="color:${scCol};font-family:'Orbitron',monospace;font-size:10px">${sc}</td>
          <td${rColor} style="font-size:10px">${reason||'--'}</td>
          <td style="color:var(--muted);font-size:9px">${(ts||'').slice(0,10)}</td>
        </tr>`;
      });
      cb.innerHTML=h+'</table>';
    } else { cb.innerHTML='<div class="empty">NO EXECUTION RECORDS</div>'; }

    // Style breakdown
    const sbd=document.getElementById('style-breakdown');
    const ss=s.style_stats||{};
    if(Object.keys(ss).length>0){
      let h='';
      Object.entries(ss).forEach(([style,data])=>{
        const wr=data.total>0?Math.round(data.wins/data.total*100):0;
        const em=style==='day'?'📈':'🌊';
        const pCol=data.pnl>=0?'var(--green)':'var(--red)';
        const wrCol=wr>=50?'var(--green)':'var(--red)';
        h+=`<div class="style-row">
          <span class="style-emo">${em}</span>
          <span class="style-name">${style.toUpperCase()}</span>
          <span style="color:var(--muted);font-size:10px;flex:1">${data.total} trades</span>
          <span class="style-wr" style="color:${wrCol};border-color:${wrCol}33">${wr}% WR</span>
          <span style="color:${pCol};font-family:'Orbitron',monospace;font-size:11px;margin-left:8px;font-weight:700">${data.pnl>=0?'+':''}$${fmt(data.pnl)}</span>
        </div>`;
      });
      sbd.innerHTML=h;
    } else { sbd.innerHTML='<div class="empty" style="padding:12px">AWAITING TRADE DATA</div>'; }

    document.getElementById('last-upd').textContent='SYNC: '+d.now;
  }catch(e){console.error(e)}
}

tick(); setInterval(tick,5000);
</script>
</body>
</html>"""

@app.route("/")
def dashboard(): return render_template_string(HTML)

@app.route("/api/data")
def api_data():
    stats=get_stats(); prices=get_prices(); fg_val,fg_lbl,fg_date=get_fear_greed()
    return jsonify({"stats":stats,"prices":prices,"fg_value":fg_val,"fg_label":fg_lbl,"fg_date":fg_date,"now":datetime.now().strftime("%H:%M:%S")})

@app.route("/health")
def health(): return {"status":"ok"}

if __name__=="__main__":
    port=int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)
