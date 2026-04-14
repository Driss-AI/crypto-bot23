"""Patch dashboard.py to use CoinGecko instead of ccxt for prices"""

old_imports = """import os
import json
import ccxt
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string
from dotenv import load_dotenv"""

new_imports = """import os
import json
import urllib.request
from datetime import datetime
from flask import Flask, render_template_string
from dotenv import load_dotenv"""

old_setup = """app = Flask(__name__)
exchange = ccxt.binance()

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]"""

new_setup = """app = Flask(__name__)

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

COINGECKO_IDS = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
    "SOL/USDT": "solana",
    "BNB/USDT": "binancecoin",
}"""

old_prices = """def get_prices():
    prices = {}
    for symbol in COINS:
        try:
            ticker = exchange.fetch_ticker(symbol)
            prices[symbol] = {
                "price": ticker["last"],
                "change": ticker["percentage"],
            }
        except:
            prices[symbol] = {"price": 0, "change": 0}
    return prices"""

new_prices = """def get_prices():
    prices = {}
    try:
        ids = ",".join(COINGECKO_IDS.values())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "DrissBotDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        for symbol, cg_id in COINGECKO_IDS.items():
            coin_data = data.get(cg_id, {})
            prices[symbol] = {
                "price" : coin_data.get("usd", 0),
                "change": coin_data.get("usd_24h_change", 0),
            }
    except Exception as e:
        print(f"Price fetch error: {e}")
        for symbol in COINS:
            prices[symbol] = {"price": 0, "change": 0}
    return prices"""

with open("dashboard.py") as f:
    content = f.read()

content = content.replace(old_imports, new_imports)
content = content.replace(old_setup, new_setup)
content = content.replace(old_prices, new_prices)

with open("dashboard.py", "w") as f:
    f.write(content)

# Verify
if "coingecko" in content.lower():
    print("✅ dashboard.py patched to use CoinGecko!")
else:
    print("⚠️ Patch may not have applied — check manually")
