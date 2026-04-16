"""
ECONOMIC CALENDAR - ForexFactory (free, no key needed)
Blocks trading 30min before high-impact events.
"""
import json, urllib.request
from datetime import datetime, timezone, timedelta

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
RELEVANT = {"USD", "EUR", "GBP", "JPY", "CNY", "All"}

def fetch_calendar():
    try:
        req = urllib.request.Request(FF_URL, headers={"User-Agent": "DrissBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"Calendar error: {e}"); return []

def parse_time(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except: return None

def is_news_blackout():
    now = datetime.now(timezone.utc)
    for ev in fetch_calendar():
        if ev.get("impact") != "High": continue
        if ev.get("country") not in RELEVANT: continue
        dt = parse_time(ev.get("date",""))
        if not dt: continue
        diff = int((dt - now).total_seconds() / 60)
        if -15 <= diff <= 30:
            label = f"in {diff}min" if diff >= 0 else f"{abs(diff)}min ago"
            return True, f"NEWS BLACKOUT: {ev['title']} ({ev['country']}) {label}"
    return False, ""

def get_macro_context():
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=12)
    events = []
    for ev in fetch_calendar():
        if ev.get("impact") != "High": continue
        if ev.get("country") not in RELEVANT: continue
        dt = parse_time(ev.get("date",""))
        if dt and now <= dt <= cutoff:
            diff = int((dt - now).total_seconds() / 60)
            events.append(f"  {dt.strftime('%H:%M')} UTC | {ev['country']} | {ev['title']} | in {diff}min | forecast:{ev.get('forecast','?')} prev:{ev.get('previous','?')}")
    if not events:
        return "No high-impact events next 12h. Clear to trade."
    header = "HIGH-IMPACT EVENTS NEXT 12H (trade carefully!):"
    if any(int(e.split('in ')[1].split('min')[0]) <= 60 for e in events if 'in ' in e):
        header = "WARNING: MAJOR EVENT WITHIN 60MIN - reduce size or skip!"
    return header + chr(10) + chr(10).join(events[:5])
