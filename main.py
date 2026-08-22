import os
import requests

def send_telegram_alert(message):
  # Reads from GitHub Secrets if available; falls back to your credentials locally
  bot_token = os.getenv(
      'TELEGRAM_BOT_TOKEN', '8894245553:AAHNms2CBjhU5yWxgcEPaHffuZ1ocLtkU68'
  )
  chat_id = os.getenv('TELEGRAM_CHAT_ID', '1715656740')

  url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
  payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}

  try:
    response = requests.post(url, json=payload, timeout=10)
    if response.status_code == 200:
      print('Telegram notification sent successfully.')
    else:
      print(f'Failed to send Telegram message: {response.text}')
  except Exception as e:
    print(f'Error sending Telegram alert: {e}')

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
    """Backup fetch directly from Yahoo Finance JSON endpoint."""
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
    # Multi-Asset Watchlist
    etfs = {
        'Nifty 50': 'NIFTYBEES.NS',
        'Bank Nifty': 'BANKBEES.NS',
        'Nifty Next 50': 'JUNIORBEES.NS',
        'Midcap 150': 'MID150BEES.NS',
        'Nasdaq 100': 'MON100.NS',
        'Gold BeES': 'GOLDBEES.NS'
    }

    threshold = -0.40  # Alert triggered on drops >= 0.40%
    triggers = []
    daily_summary = []

    print("Checking real-time market data across ETF basket...")
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
                raise ValueError("Primary API returned non-success")

        except Exception:
            print(f"Primary API unavailable for {ticker}. Using Yahoo fallback...")
            try:
                percent_change, last_price = get_yahoo_fallback(ticker)
                source = " *(via Fallback)*"
            except Exception as yf_err:
                print(f"Fallback failed for {ticker}: {yf_err}")
                continue

        # Add to the daily summary list
        change_sign = "+" if percent_change >= 0 else ""
        daily_summary.append(f"• *{name}*: `{change_sign}{percent_change:.2f}%` (₹{last_price:.2f})")

        # Check if drop qualifies for buy alert
        if percent_change <= threshold:
            triggers.append(
                f"• *{name}* (`{ticker}`)\n"
                f"  Drop: *{percent_change:.2f}%*\n"
                f"  LTP: ₹{last_price:.2f}{source}"
            )

    # Dispatch appropriate Telegram notification
    if triggers:
        alert_text = (
            "🚨 *MARKET DIP ALERT (≥ 0.4% Drop)* 🚨\n\n"
            + "\n\n".join(triggers)
            + "\n\n💡 _Log into your broker app to review and place manual orders._"
        )
        print("Triggers detected! Dispatching Telegram buy alert...")
        send_telegram_alert(alert_text)
    else:
        no_drop_text = (
            "✅ *DAILY MARKET UPDATE (No Action Needed)*\n\n"
            "No ETF on your watchlist dropped $\\ge 0.40\\%$ today.\n\n"
            "*Today's Closes / Moves:*\n"
            + "\n".join(daily_summary)
            + "\n\n😴 _Keep your cash dry and enjoy your evening!_"
        )
        print("No ETF dropped beyond 0.4%. Sending daily summary ping...")
        send_telegram_alert(no_drop_text)

if __name__ == '__main__':
    check_market_dips()
