import os
import csv
import json
import requests
from datetime import datetime
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

NIFTY_THRESHOLD = -0.40
BUY_AMOUNT_BASE = 250
MONTHLY_LIMIT = 5000

# Profit-taking targets (%)
PROFIT_TARGETS = [5, 10, 15, 20]

# Volatility filter: skip buy if N+ indices are down hard
SYSTEMIC_CRASH_THRESHOLD = 3  # indices down ≥0.5%

# Rebalancing: reduce buy size if <50% budget remaining
REBALANCE_THRESHOLD = 0.50

LOG_FILE = Path("niftybees_signals.csv")
PORTFOLIO_FILE = Path("portfolio_state.json")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_alert(message):
    """Send Telegram message."""
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Telegram credentials missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            print("✅ Telegram sent successfully")
            return True
        
        print(f"❌ Telegram API error: {data}")
        return False

    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


# ============================================================
# YAHOO FINANCE
# ============================================================

def get_yahoo_data(ticker):
    """Fetch market data from Yahoo Finance."""
    
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()

    result = data["chart"]["result"][0]
    meta = result["meta"]

    current_price = float(meta["regularMarketPrice"])
    previous_close = float(meta.get("chartPreviousClose", meta.get("previousClose")))

    if previous_close == 0:
        raise ValueError(f"Previous close is zero for {ticker}")

    percent_change = ((current_price - previous_close) / previous_close) * 100

    return percent_change, current_price, previous_close


# ============================================================
# PORTFOLIO STATE MANAGEMENT
# ============================================================

def load_portfolio_state():
    """Load portfolio state from JSON."""
    
    if not PORTFOLIO_FILE.exists():
        return {
            "total_invested": 0.0,
            "total_shares": 0.0,
            "cost_basis": 0.0,
            "last_profit_target_alerted": 0,
            "purchase_history": []
        }

    try:
        with open(PORTFOLIO_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load portfolio state: {e}")
        return {
            "total_invested": 0.0,
            "total_shares": 0.0,
            "cost_basis": 0.0,
            "last_profit_target_alerted": 0,
            "purchase_history": []
        }


def save_portfolio_state(state):
    """Save portfolio state to JSON."""
    
    try:
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print("✅ Portfolio state saved")
    except Exception as e:
        print(f"❌ Could not save portfolio state: {e}")


def update_portfolio_after_buy(buy_amount, niftybees_price, state):
    """Update portfolio after a buy."""
    
    shares_bought = buy_amount / niftybees_price
    
    state["total_invested"] += buy_amount
    state["total_shares"] += shares_bought
    
    if state["total_shares"] > 0:
        state["cost_basis"] = state["total_invested"] / state["total_shares"]
    
    state["purchase_history"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "amount": buy_amount,
        "price": niftybees_price,
        "shares": shares_bought,
        "cost_basis": state["cost_basis"]
    })
    
    return state


# ============================================================
# MONTHLY SPENDING
# ============================================================

def get_current_month_spend():
    """Calculate monthly spend."""
    
    if not LOG_FILE.exists():
        return 0.0

    current_month = datetime.now().strftime("%Y-%m")
    total = 0.0

    try:
        with open(LOG_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = row.get("timestamp", "")
                if not timestamp.startswith(current_month):
                    continue
                try:
                    amount = float(row.get("buy_amount", 0))
                    total += amount
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"❌ Could not read signal log: {e}")

    return total


def signal_already_logged_today():
    """Check if today already has a logged buy signal."""
    
    if not LOG_FILE.exists():
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    try:
        with open(LOG_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = row.get("timestamp", "")
                if timestamp.startswith(today):
                    return True
    except Exception as e:
        print(f"❌ Could not check today's signals: {e}")

    return False


# ============================================================
# LOGGING
# ============================================================

def log_signal(nifty_change, nifty_price, niftybees_price, buy_amount, monthly_spend, state):
    """Log buy signal to CSV."""
    
    file_exists = LOG_FILE.exists()
    fields = [
        "timestamp",
        "nifty_change",
        "nifty_price",
        "niftybees_price",
        "buy_amount",
        "monthly_spend",
        "total_invested",
        "total_shares",
        "cost_basis"
    ]

    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if not file_exists:
                writer.writeheader()
            
            writer.writerow({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nifty_change": round(nifty_change, 4),
                "nifty_price": round(nifty_price, 2),
                "niftybees_price": round(niftybees_price, 2),
                "buy_amount": buy_amount,
                "monthly_spend": round(monthly_spend, 2),
                "total_invested": round(state["total_invested"], 2),
                "total_shares": round(state["total_shares"], 4),
                "cost_basis": round(state["cost_basis"], 2)
            })

        print(f"✅ Signal logged to {LOG_FILE}")
    except Exception as e:
        print(f"❌ Could not write signal log: {e}")


# ============================================================
# MARKET CONTEXT
# ============================================================

def get_market_context():
    """Fetch other indices for context."""
    
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
            change, price, _ = get_yahoo_data(ticker)
            results[name] = {"change": change, "price": price}
        except Exception as e:
            print(f"⚠️  Could not fetch {name}: {e}")

    return results


def format_market_context(context):
    """Format market context for Telegram."""
    
    if not context:
        return "No additional market data available."

    lines = []
    for name, data in context.items():
        change = data["change"]
        lines.append(f"• {name}: `{change:+.2f}%`")

    return "\n".join(lines)


# ============================================================
# VOLATILITY FILTER
# ============================================================

def is_systemic_crash(context):
    """Check if multiple indices are down hard (panic crash)."""
    
    down_count = sum(
        1 for idx in context.values() 
        if idx["change"] <= -0.5
    )
    
    is_crash = down_count >= SYSTEMIC_CRASH_THRESHOLD
    
    if is_crash:
        print(
            f"⚠️  SYSTEMIC CRASH DETECTED: "
            f"{down_count} indices down ≥0.5%"
        )
    
    return is_crash


# ============================================================
# DYNAMIC BUY AMOUNT
# ============================================================

def calculate_dynamic_buy_amount(nifty_change, remaining_budget):
    """
    Pyramid strategy: bigger dips = bigger buys.
    More aggressive on larger drops.
    """
    
    if nifty_change <= -1.0:  # >1% drop
        buy_amount = 500
        severity = "SEVERE"
    elif nifty_change <= -0.7:  # 0.7-1% drop
        buy_amount = 350
        severity = "HIGH"
    elif nifty_change <= -0.4:  # 0.4-0.7% drop
        buy_amount = 250
        severity = "MODERATE"
    else:
        buy_amount = 250
        severity = "LIGHT"
    
    print(f"📊 Dip severity: {severity} ({nifty_change:.2f}%)")
    print(f"💰 Dynamic buy amount: ₹{buy_amount}")
    
    return min(buy_amount, remaining_budget)


# ============================================================
# REBALANCING
# ============================================================

def apply_rebalancing(remaining_budget, remaining_pct):
    """Reduce buy size if approaching monthly limit."""
    
    if remaining_pct < REBALANCE_THRESHOLD:
        reduction_factor = remaining_pct / REBALANCE_THRESHOLD
        print(
            f"🔄 REBALANCING: {remaining_pct*100:.0f}% budget remaining. "
            f"Reducing buy size by {(1-reduction_factor)*100:.0f}%"
        )
        return True, reduction_factor
    
    return False, 1.0


# ============================================================
# PROFIT TAKING
# ============================================================

def check_profit_targets(state, current_price):
    """Alert when position hits profit targets."""
    
    if state["total_shares"] <= 0 or state["total_invested"] <= 0:
        return None, []

    current_value = state["total_shares"] * current_price
    unrealized_pl = current_value - state["total_invested"]
    unrealized_pct = (unrealized_pl / state["total_invested"]) * 100

    # Find which targets have been hit
    new_alerts = []
    for target in PROFIT_TARGETS:
        if unrealized_pct >= target and target > state["last_profit_target_alerted"]:
            new_alerts.append(target)

    portfolio_stats = {
        "current_value": current_value,
        "unrealized_pl": unrealized_pl,
        "unrealized_pct": unrealized_pct,
        "cost_basis": state["cost_basis"],
        "total_shares": state["total_shares"],
        "total_invested": state["total_invested"]
    }

    return portfolio_stats, new_alerts


def format_portfolio_status(stats):
    """Format portfolio for Telegram."""
    
    lines = [
        "💼 *PORTFOLIO STATUS*",
        f"Cost basis: `₹{stats['cost_basis']:.2f}`",
        f"Shares held: `{stats['total_shares']:.4f}`",
        f"Total invested: `₹{stats['total_invested']:.0f}`",
        f"Current value: `₹{stats['current_value']:.0f}`",
        f"Unrealized: `{stats['unrealized_pl']:+.0f}` ({stats['unrealized_pct']:+.2f}%)"
    ]
    return "\n".join(lines)


# ============================================================
# MAIN STRATEGY
# ============================================================

def check_market_dip():
    
    print("=" * 70)
    print("NIFTYBEES DIP ACCUMULATION STRATEGY (ENHANCED)")
    print("=" * 70)
    print()

    # Load portfolio state
    state = load_portfolio_state()

    print(f"📍 Signal threshold: {NIFTY_THRESHOLD:.2f}%")
    print(f"💰 Base buy amount: ₹{BUY_AMOUNT_BASE}")
    print(f"📅 Monthly limit: ₹{MONTHLY_LIMIT}")
    print()

    # ============================================================
    # GET NIFTY 50
    # ============================================================

    try:
        nifty_change, nifty_price, nifty_previous = get_yahoo_data("^NSEI")
        print(f"📈 Nifty 50: {nifty_change:+.2f}% | Price: ₹{nifty_price:.2f}")
    except Exception as e:
        print(f"❌ ERROR: Could not fetch Nifty 50: {e}")
        return

    # ============================================================
    # GET NIFTYBEES
    # ============================================================

    try:
        niftybees_change, niftybees_price, niftybees_previous = get_yahoo_data("NIFTYBEES.NS")
        print(f"🐝 NIFTYBEES: ₹{niftybees_price:.2f} ({niftybees_change:+.2f}%)")
    except Exception as e:
        print(f"❌ ERROR: Could not fetch NIFTYBEES: {e}")
        return

    # ============================================================
    # GET MARKET CONTEXT
    # ============================================================

    context = get_market_context()
    context_text = format_market_context(context)

    print()
    print("🌍 Market Context:")
    print(context_text)
    print()

    # ============================================================
    # CHECK PORTFOLIO STATUS
    # ============================================================

    portfolio_stats, profit_alerts = check_profit_targets(state, niftybees_price)

    if portfolio_stats:
        print(format_portfolio_status(portfolio_stats))
        print()

    # ============================================================
    # MONTHLY ALLOCATION
    # ============================================================

    monthly_spend = get_current_month_spend()
    remaining_budget = MONTHLY_LIMIT - monthly_spend
    remaining_pct = remaining_budget / MONTHLY_LIMIT

    print(f"💳 Monthly invested: ₹{monthly_spend:.0f}")
    print(f"💵 Remaining budget: ₹{remaining_budget:.0f} ({remaining_pct*100:.0f}%)")
    print()

    # ============================================================
    # PROFIT TAKING ALERTS
    # ============================================================

    if profit_alerts and portfolio_stats:
        for target in profit_alerts:
            message = (
                f"🎯 *PROFIT TARGET HIT: +{target}%*\n\n"
                f"Position is now {portfolio_stats['unrealized_pct']:+.2f}% in profit.\n\n"
                f"{format_portfolio_status(portfolio_stats)}\n\n"
                f"📌 Consider taking profits or rebalancing.\n\n"
                f"⚠️ _This is a signal only. Not financial advice._"
            )
            send_telegram_alert(message)
            state["last_profit_target_alerted"] = target

    # ============================================================
    # CHECK FOR DUPLICATE TODAY
    # ============================================================

    if signal_already_logged_today():
        print("⏸️  Today's buy signal already logged. Skipping.")
        print()
        
        # But still check for profit targets
        if portfolio_stats:
            print("📊 Portfolio update sent (profit targets checked)")
        
        return

    # ============================================================
    # VOLATILITY FILTER
    # ============================================================

    if is_systemic_crash(context):
        print()
        print("🚫 SKIPPING BUY: Systemic market crash detected")
        print()
        
        message = (
            "⚠️ *MARKET CRASH ALERT*\n\n"
            f"Nifty: {nifty_change:+.2f}%\n\n"
            f"Multiple indices down ≥0.5%. "
            "Buy signal suppressed due to systemic risk.\n\n"
            "💡 Consider sitting tight until stabilization."
        )
        send_telegram_alert(message)
        return

    # ============================================================
    # CHECK DIP CONDITION
    # ============================================================

    if nifty_change <= NIFTY_THRESHOLD:

        print()
        print("🚨 NIFTY DIP DETECTED!")
        print(f"   Nifty down {nifty_change:.2f}%")
        print()

        # ========================================================
        # CHECK MONTHLY LIMIT
        # ========================================================

        if remaining_budget <= 0:
            print("❌ Monthly allocation limit reached!")
            print()
            
            message = (
                "⚠️ *DIP DETECTED BUT LIMIT REACHED*\n\n"
                f"📉 Nifty: {nifty_change:+.2f}%\n"
                f"💰 NIFTYBEES: ₹{niftybees_price:.2f}\n\n"
                f"🚫 NO BUY - Monthly limit reached\n\n"
                f"Allocated: ₹{monthly_spend:.0f} / ₹{MONTHLY_LIMIT:.0f}"
            )
            send_telegram_alert(message)
            return

        # ========================================================
        # CALCULATE DYNAMIC BUY AMOUNT
        # ========================================================

        buy_amount = calculate_dynamic_buy_amount(nifty_change, remaining_budget)

        # ========================================================
        # APPLY REBALANCING
        # ========================================================

        should_rebalance, reduction_factor = apply_rebalancing(remaining_budget, remaining_pct)
        if should_rebalance:
            buy_amount = int(buy_amount * reduction_factor)
            print(f"✂️  Rebalanced buy amount: ₹{buy_amount}")

        # Final safety check
        buy_amount = min(buy_amount, remaining_budget)

        new_monthly_spend = monthly_spend + buy_amount

        # ========================================================
        # UPDATE PORTFOLIO
        # ========================================================

        state = update_portfolio_after_buy(buy_amount, niftybees_price, state)

        # ========================================================
        # LOG
        # ========================================================

        log_signal(
            nifty_change=nifty_change,
            nifty_price=nifty_price,
            niftybees_price=niftybees_price,
            buy_amount=buy_amount,
            monthly_spend=new_monthly_spend,
            state=state
        )

        # ========================================================
        # SAVE PORTFOLIO STATE
        # ========================================================

        save_portfolio_state(state)

        # ========================================================
        # BUILD TELEGRAM MESSAGE
        # ========================================================

        message = (
            "🟢 *NIFTYBEES BUY SIGNAL*\n\n"
            f"📉 Nifty 50: *{nifty_change:+.2f}%*\n"
            f"📊 Nifty level: `{nifty_price:.2f}`\n"
            f"💰 NIFTYBEES: `₹{niftybees_price:.2f}`\n\n"
            f"🛒 *BUY: ₹{buy_amount}*\n\n"
        )

        if portfolio_stats:
            message += (
                f"{format_portfolio_status(portfolio_stats)}\n\n"
            )

        message += (
            "📌 *Strategy*\n"
            "• Nifty falls ≥ 0.40% → Buy NIFTYBEES\n"
            "• Pyramid: Bigger dips = Bigger buys\n"
            "• Hold for long-term wealth accumulation\n"
            "• Target +5%, +10%, +15%, +20%\n\n"
            f"💼 *Monthly Allocation*\n"
            f"₹{new_monthly_spend:.0f} / ₹{MONTHLY_LIMIT:.0f}\n\n"
            "🌍 *Market Context*\n"
            f"{context_text}\n\n"
            "⚠️ _Strategy signal only. Not financial advice._"
        )

        send_telegram_alert(message)

        print()
        print("✅ BUY SIGNAL EXECUTED")
        print()

    # ============================================================
    # NO SIGNAL - JUST UPDATES
    # ============================================================

    else:
        print()
        print(f"✅ No buy signal (Nifty: {nifty_change:+.2f}%, need ≤{NIFTY_THRESHOLD:.2f}%)")
        print()

        # Send daily portfolio update if holding positions
        if portfolio_stats and state["total_shares"] > 0:
            message = (
                "📊 *DAILY PORTFOLIO UPDATE*\n\n"
                f"Nifty 50: {nifty_change:+.2f}%\n"
                f"No buy signal today.\n\n"
                f"{format_portfolio_status(portfolio_stats)}\n\n"
                "🌍 *Market Context*\n"
                f"{context_text}\n\n"
                "💡 _Monitoring for next dip..._"
            )
            send_telegram_alert(message)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        check_market_dip()
    except Exception as e:
        print()
        print("❌ UNEXPECTED ERROR:")
        print(e)
        
        # Send error alert
        error_message = (
            f"🚨 *SCRIPT ERROR*\n\n"
            f"```\n{str(e)}\n```\n\n"
            "Check GitHub Actions logs."
        )
        send_telegram_alert(error_message)
