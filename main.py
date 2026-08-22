import os
import requests

def send_telegram_alert(message):
    bot_token = os.getenv(
        'TELEGRAM_BOT_TOKEN', 
        '8894245553:AAHNms2CBjhU5yWxgcEPaHffuZ1ocLtkU68'
    ).strip()
    chat_id = str(os.getenv('TELEGRAM_CHAT_ID', '1715656740')).strip()

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {
        'chat_id': chat_id, 
        'text': message, 
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and data.get('ok'):
            print("Telegram notification sent successfully.")
        else:
            print(f"Failed to send Telegram message: {data}")
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")

def get_yahoo_fallback(ticker):
    """Fetches index data directly from Yahoo Finance."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json()
    
    meta = data['chart']['result'][0]['meta']
    last_price = float(meta['regularMarketPrice'])
    prev_close = float(meta['chartPreviousClose'])
    percent_change = ((last_price - prev_close) / prev_close) * 100
    
    return percent_change, last_price

def check_market_dips():
    # 📊 GLOBAL & DOMESTIC INDEX WATCHLIST
    indices = {
        'Nifty 50': '^NSEI',
        'Bank Nifty': '^NSEBANK',
        'Nifty IT': '^CNXIT',
        'Sensex': '^BSESN',
        'Nasdaq 100': '^NDX',
        'S&P 500': '^GSPC'
    }

    threshold = -0.40  # Alert triggered on drops >= 0.40%
    triggers = []
    daily_summary = []

    print("Checking real-time market data across Index basket...")
    base_url = "http://65.0.104.9/stock"
    headers = {"User-Agent": "Mozilla/5.0"}

    for name, ticker in indices.items():
        try:
            # The primary API might not support '^' index symbols.
            # If it fails, it instantly drops into the Yahoo fallback.
            response = requests.get(f"{base_url}?symbol={ticker}&res=num", headers=headers, timeout=5)
            data = response.json()

            if data.get('status') == 'success':
                stock_data = data.get('data', {})
                percent_change = float(stock_data.get('percent_change', 0.0))
                last_price = float(stock_data.get('last_price', 0.0))
                source = ""
            else:
                raise ValueError("Primary API non-success (likely doesn't support indices)")

        except Exception:
            print(f"Primary API bypassed for {ticker}. Fetching from Yahoo Finance...")
            try:
                percent_change, last_price = get_yahoo_fallback(ticker)
                source = " *(via Yahoo)*"
            except Exception as yf_err:
                print(f"Fallback failed for {ticker}: {yf_err}")
                continue

        # Format positive/negative signs for the daily summary
        change_sign = "+" if percent_change >= 0 else ""
        
        # We don't use ₹ for Nasdaq/S&P since they are in USD, so we keep it generic
        currency = "$" if ticker in ['^NDX', '^GSPC'] else "₹"
        daily_summary.append(f"• *{name}*: `{change_sign}{percent_change:.2f}%` ({currency}{last_price:.2f})")

        # Check if drop qualifies for alert
        if percent_change <= threshold:
            triggers.append(
                f"• *{name}* (`{ticker}`)\n"
                f"  Drop: *{percent_change:.2f}%*\n"
                f"  Level: {currency}{last_price:.2f}{source}"
            )

    # Dispatch appropriate Telegram notification
    if triggers:
        alert_text = (
            "🚨 *MAJOR INDEX DIP ALERT (≥ 0.4% Drop)* 🚨\n\n"
            + "\n\n".join(triggers)
            + "\n\n💡 _Log into your broker app to deploy capital into ETFs._"
        )
        print("Triggers detected! Dispatching Telegram alert...")
        send_telegram_alert(alert_text)
    else:
        no_drop_text = (
            "✅ *DAILY INDEX UPDATE (No Action Needed)*\n\n"
            "No major index dropped ≥ 0.40% today.\n\n"
            "*Today's Closes / Moves:*\n"
            + "\n".join(daily_summary)
            + "\n\n😴 _Keep your cash dry and enjoy your evening!_"
        )
        print("No index dropped beyond 0.4%. Sending daily summary ping...")
        send_telegram_alert(no_drop_text)

if __name__ == '__main__':
    check_market_dips()
