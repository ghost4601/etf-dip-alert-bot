import os
import requests


def send_telegram_alert(message):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        print("Telegram secrets not configured. Please check GitHub Secrets.")
        return

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("Telegram notification sent successfully.")
        else:
            print(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")


def get_yahoo_fallback(ticker):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json()

    meta = data['chart']['result'][0]['meta']
    last_price = float(meta['regularMarketPrice'])
    prev_close = float(meta['chartPreviousClose'])
    percent_change = ((last_price - prev_close) / prev_close) * 100

    return percent_change, last_price


def check_market_dips():
    etfs = {
        'Nifty 50': 'NIFTYBEES.NS',
        'Bank Nifty': 'BANKBEES.NS',
        'Next 50': 'JUNIORBEES.NS'
    }

    threshold = -0.40  # Trigger when drop is >= 0.40%
    triggers = []

    print("Fetching real-time data...")
    base_url = "http://65.0.104.9/stock"
    headers = {"User-Agent": "Mozilla/5.0"}

    for name, ticker in etfs.items():
        try:
            response = requests.get(f"{base_url}?symbol={ticker}&res=num", headers=headers, timeout=5)
            data = response.json()

            if data.get('status') == 'success':
                stock_data = data.get('data', {})
                percent_change = float(stock_data.get('percent_change', 0.0))
                last_price = float(stock_data.get('last_price', 0.0))
                source = ""
            else:
                raise ValueError("API non-success status.")

        except Exception:
            print(f"Primary API unavailable for {ticker}. Switching to Yahoo fallback...")
            try:
                percent_change, last_price = get_yahoo_fallback(ticker)
                source = " *(via Fallback)*"
            except Exception as yf_e:
                print(f"Fallback also failed for {ticker}: {yf_e}")
                continue

        if percent_change <= threshold:
            triggers.append(
                f"• *{name}* (`{ticker}`)\n"
                f"  Drop: *{percent_change:.2f}%*\n"
                f"  LTP: ₹{last_price:.2f}{source}"
            )

    if triggers:
        alert_text = (
                "🚨 *MARKET DIP ALERT (≥ 0.4% Drop)* 🚨\n\n"
                + "\n\n".join(triggers)
                + "\n\n💡 _Open your broker app to review and deploy capital._"
        )
        print("Conditions met. Sending alert...")
        send_telegram_alert(alert_text)
    else:
        print("No ETF dropped beyond 0.4% today. All quiet.")


if __name__ == '__main__':
    check_market_dips()