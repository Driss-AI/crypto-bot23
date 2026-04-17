import urllib.request
import json
import datetime

def get_latest_news():
    print(" Fetching crypto sentiment...")
    all_articles = []

    #  SOURCE 1: Reddit r/Bitcoin 
    try:
        url = "https://www.reddit.com/r/Bitcoin/hot.json?limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            posts = data["data"]["children"]
            for post in posts:
                title = post["data"]["title"]
                score = post["data"]["score"]
                all_articles.append({
                    "source": "r/Bitcoin",
                    "title" : title,
                    "score" : score,
                })
        print(f" Reddit r/Bitcoin: {len(all_articles)} posts")
    except Exception as e:
        print(f" Reddit failed: {e}")

    #  SOURCE 2: Reddit r/CryptoCurrency 
    try:
        url = "https://www.reddit.com/r/CryptoCurrency/hot.json?limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            posts = data["data"]["children"]
            for post in posts:
                title = post["data"]["title"]
                score = post["data"]["score"]
                all_articles.append({
                    "source": "r/CryptoCurrency",
                    "title" : title,
                    "score" : score,
                })
        print(f" Reddit r/CryptoCurrency: {len(all_articles)} posts")
    except Exception as e:
        print(f" Reddit r/CryptoCurrency failed: {e}")

    #  SOURCE 3: Fear & Greed Index 
    fng_text = ""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            fng   = data["data"][0]
            value = int(fng["value"])
            label = fng["value_classification"]

            if value <= 25:
                mood = " EXTREME FEAR  possible buy opportunity"
            elif value <= 45:
                mood = " FEAR  market is worried"
            elif value <= 55:
                mood = " NEUTRAL  no strong sentiment"
            elif value <= 75:
                mood = " GREED  investors are excited"
            else:
                mood = " EXTREME GREED  possible sell opportunity"

            fng_text = f"\n FEAR & GREED INDEX: {value}/100  {label}\n   {mood}\n"
            print(f" Fear & Greed: {value}/100 ({label})")
    except Exception as e:
        print(f" Fear & Greed failed: {e}")

    #  FORMAT FOR CLAUDE 
    news_text = " CRYPTO SENTIMENT:\n"
    news_text += "-" * 40 + "\n"

    if all_articles:
        news_text += " Trending on Reddit:\n"
        for i, article in enumerate(all_articles[:8], 1):
            news_text += f"{i}. [{article['source']}] {article['title']}\n"

    if fng_text:
        news_text += fng_text

    if not all_articles and not fng_text:
        return "No sentiment data available."

    return news_text

#  TEST 
if __name__ == "__main__":
    news = get_latest_news()
    print("\n" + news)