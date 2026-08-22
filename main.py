import os
import csv
import requests
from datetime import datetime
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

# Strategy:
# If Nifty 50 falls by 0.40% or more in the current session,
# generate a NIFTYBEES buy signal.

NIFTY_THRESHOLD = -0.40

# Amount to buy per signal
BUY_AMOUNT = 250

# Maximum amount to deploy per calendar month
MONTHLY_LIMIT = 5000

# Local signal log
LOG_FILE = Path("niftybees_signals.csv")

# GitHub Actions / environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_alert(message):
    """
    Send a Telegram message using environment variables.
    """

    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not configured.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID is not configured.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("ok"):
            print("Telegram notification sent successfully.")
            return True

        print(f"Telegram API error: {data}")
        return False

    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ============================================================
# YAHOO FINANCE DATA
# ============================================================

def get_yahoo_data(ticker):
    """
    Fetch current market data from Yahoo Finance.

    Returns:
        percent_change
        current_price
        previous_close
    """

    url = (
        f"https://query2.finance.yahoo.com/"
        f"v8/finance/chart/{ticker}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    result = data["chart"]["result"][0]

    meta = result["meta"]

    current_price = float(
        meta["regularMarketPrice"]
    )

    previous_close = float(
        meta.get(
            "chartPreviousClose",
            meta.get("previousClose")
        )
    )

    if previous_close == 0:
        raise ValueError(
            f"Previous close is zero for {ticker}"
        )

    percent_change = (
        (current_price - previous_close)
        / previous_close
    ) * 100

    return (
        percent_change,
        current_price,
        previous_close
    )


# ============================================================
# MONTHLY SPENDING
# ============================================================

def get_current_month_spend():
    """
    Calculate how much has already been allocated
    during the current calendar month.
    """

    if not LOG_FILE.exists():
        return 0.0

    current_month = datetime.now().strftime("%Y-%m")

    total = 0.0

    try:

        with open(
            LOG_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                timestamp = row.get(
                    "timestamp",
                    ""
                )

                if not timestamp.startswith(
                    current_month
                ):
                    continue

                try:

                    amount = float(
                        row.get(
                            "buy_amount",
                            0
                        )
                    )

                    total += amount

                except (
                    ValueError,
                    TypeError
                ):
                    continue

    except Exception as e:

        print(
            f"Could not read signal log: {e}"
        )

    return total


# ============================================================
# CHECK WHETHER TODAY ALREADY GENERATED A SIGNAL
# ============================================================

def signal_already_logged_today():
    """
    Prevent duplicate purchases if the script runs
    multiple times on the same day.
    """

    if not LOG_FILE.exists():
        return False

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    try:

        with open(
            LOG_FILE,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                timestamp = row.get(
                    "timestamp",
                    ""
                )

                if timestamp.startswith(today):
                    return True

    except Exception as e:

        print(
            f"Could not check today's signals: {e}"
        )

    return False


# ============================================================
# LOG SIGNAL
# ============================================================

def log_signal(
    nifty_change,
    nifty_price,
    niftybees_price,
    buy_amount,
    monthly_spend
):
    """
    Save each buy signal to CSV.
    """

    file_exists = LOG_FILE.exists()

    fields = [
        "timestamp",
        "nifty_change",
        "nifty_price",
        "niftybees_price",
        "buy_amount",
        "monthly_spend"
    ]

    try:

        with open(
            LOG_FILE,
            "a",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=fields
            )

            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "timestamp": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "nifty_change": round(
                    nifty_change,
                    4
                ),
                "nifty_price": round(
                    nifty_price,
                    2
                ),
                "niftybees_price": round(
                    niftybees_price,
                    2
                ),
                "buy_amount": buy_amount,
                "monthly_spend": round(
                    monthly_spend,
                    2
                )
            })

        print(
            f"Signal logged to {LOG_FILE}"
        )

    except Exception as e:

        print(
            f"Could not write signal log: {e}"
        )


# ============================================================
# MARKET CONTEXT
# ============================================================

def get_market_context():
    """
    Fetch other major indices for informational context.
    """

    indices = {
        "Bank Nifty": "^NSEBANK",
        "Nifty IT": "^CNXIT",
        "Sensex": "^BSESN",
        "Nasdaq 100": "^NDX",
        "S&P 500": "^GSPC"
    }

    results = {}

    for name, ticker in indices.items():

        try:

            change, price, _ = (
                get_yahoo_data(ticker)
            )

            results[name] = {
                "change": change,
                "price": price
            }

        except Exception as e:

            print(
                f"Could not fetch {name}: {e}"
            )

    return results


# ============================================================
# FORMAT MARKET CONTEXT
# ============================================================

def format_market_context(context):
    """
    Format context for Telegram.
    """

    if not context:
        return "No additional market data available."

    lines = []

    for name, data in context.items():

        change = data["change"]

        lines.append(
            f"• {name}: `{change:+.2f}%`"
        )

    return "\n".join(lines)


# ============================================================
# MAIN STRATEGY
# ============================================================

def check_market_dip():

    print("=" * 70)
    print("NIFTYBEES DIP ACCUMULATION STRATEGY")
    print("=" * 70)

    print(
        f"Signal threshold : {NIFTY_THRESHOLD:.2f}%"
    )

    print(
        f"Buy amount       : ₹{BUY_AMOUNT}"
    )

    print(
        f"Monthly limit    : ₹{MONTHLY_LIMIT}"
    )

    print()

    # --------------------------------------------------------
    # GET NIFTY
    # --------------------------------------------------------

    try:

        (
            nifty_change,
            nifty_price,
            nifty_previous
        ) = get_yahoo_data("^NSEI")

        print(
            f"Nifty 50         : "
            f"{nifty_change:+.2f}%"
        )

        print(
            f"Nifty price      : "
            f"{nifty_price:.2f}"
        )

        print(
            f"Previous close   : "
            f"{nifty_previous:.2f}"
        )

    except Exception as e:

        print(
            f"ERROR: Could not fetch Nifty 50: {e}"
        )

        return


    # --------------------------------------------------------
    # GET NIFTYBEES
    # --------------------------------------------------------

    try:

        (
            niftybees_change,
            niftybees_price,
            niftybees_previous
        ) = get_yahoo_data(
            "NIFTYBEES.NS"
        )

        print(
            f"NIFTYBEES        : "
            f"₹{niftybees_price:.2f}"
        )

        print(
            f"NIFTYBEES change : "
            f"{niftybees_change:+.2f}%"
        )

    except Exception as e:

        print(
            f"ERROR: Could not fetch NIFTYBEES: {e}"
        )

        return


    # --------------------------------------------------------
    # CHECK MONTHLY ALLOCATION
    # --------------------------------------------------------

    monthly_spend = (
        get_current_month_spend()
    )

    remaining_budget = (
        MONTHLY_LIMIT - monthly_spend
    )

    print()

    print(
        f"Monthly invested : "
        f"₹{monthly_spend:.0f}"
    )

    print(
        f"Remaining budget : "
        f"₹{remaining_budget:.0f}"
    )


    # --------------------------------------------------------
    # CHECK TODAY'S SIGNAL
    # --------------------------------------------------------

    already_logged = (
        signal_already_logged_today()
    )

    if already_logged:

        print()
        print(
            "Today's buy signal has already "
            "been logged."
        )

        print(
            "No duplicate purchase will be generated."
        )

        return


    # --------------------------------------------------------
    # SIGNAL CONDITION
    # --------------------------------------------------------

    if nifty_change <= NIFTY_THRESHOLD:

        print()
        print("🚨 NIFTY DIP DETECTED")
        print(
            f"Nifty is down {nifty_change:.2f}%"
        )


        # ----------------------------------------------------
        # CHECK MONTHLY LIMIT
        # ----------------------------------------------------

        if remaining_budget <= 0:

            print(
                "Monthly allocation limit reached."
            )

            message = (
                "⚠️ *NIFTYBEES DIP DETECTED*\n\n"
                f"📉 Nifty 50: "
                f"*{nifty_change:+.2f}%*\n"
                f"📊 Nifty: `{nifty_price:.2f}`\n\n"
                "🚫 *NO BUY*\n\n"
                "Monthly NIFTYBEES allocation "
                "limit has been reached.\n\n"
                f"Monthly allocation: "
                f"₹{monthly_spend:.0f} / "
                f"₹{MONTHLY_LIMIT:.0f}"
            )

            send_telegram_alert(message)

            return


        # ----------------------------------------------------
        # CALCULATE BUY AMOUNT
        # ----------------------------------------------------

        buy_amount = min(
            BUY_AMOUNT,
            remaining_budget
        )

        new_monthly_spend = (
            monthly_spend + buy_amount
        )


        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

        log_signal(
            nifty_change=nifty_change,
            nifty_price=nifty_price,
            niftybees_price=niftybees_price,
            buy_amount=buy_amount,
            monthly_spend=new_monthly_spend
        )


        # ----------------------------------------------------
        # MARKET CONTEXT
        # ----------------------------------------------------

        context = get_market_context()

        context_text = (
            format_market_context(context)
        )


        # ----------------------------------------------------
        # TELEGRAM MESSAGE
        # ----------------------------------------------------

        message = (
            "🟢 *NIFTYBEES BUY SIGNAL*\n"
            "\n"
            f"📉 Nifty 50: "
            f"*{nifty_change:+.2f}%*\n"
            f"📊 Nifty level: "
            f"`{nifty_price:.2f}`\n"
            f"💰 NIFTYBEES: "
            f"`₹{niftybees_price:.2f}`\n"
            "\n"
            f"🛒 *Suggested buy: ₹{buy_amount}*\n"
            "\n"
            "📌 *Strategy*\n"
            "• Nifty falls ≥ 0.40%\n"
            "• Buy NIFTYBEES\n"
            "• Hold indefinitely\n"
            "• Another qualifying day = another buy\n"
            "\n"
            "💰 *Monthly allocation*\n"
            f"₹{new_monthly_spend:.0f} / "
            f"₹{MONTHLY_LIMIT:.0f}\n"
            "\n"
            "🌍 *Market context*\n"
            f"{context_text}\n"
            "\n"
            "⚠️ _Strategy signal only. "
            "Not financial advice._"
        )

        send_telegram_alert(message)

        print()
        print(message)


    # --------------------------------------------------------
    # NO SIGNAL
    # --------------------------------------------------------

    else:

        print()
        print(
            "No NIFTYBEES buy signal."
        )

        print(
            f"Nifty move: "
            f"{nifty_change:+.2f}%"
        )


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        check_market_dip()

    except Exception as e:

        print()
        print(
            "Unexpected error:"
        )

        print(e)
