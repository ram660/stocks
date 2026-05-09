"""
alerts.py
=========
Handles dispatching notifications for generated signals to external platforms like Telegram.
"""
import requests
import config

def send_telegram_alert(ticker: str, signal_name: str, signal_type: str, details: str):
    """
    Sends a message to all configured TELEGRAM_CHAT_IDS if the setup is available.
    Suggests options trading actions depending on the signal type (BUY=Call, SELL=Put).
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_IDS:
        return

    # Determine recommended option
    opt_suggestion = "Calls" if signal_type.upper() == "BUY" else "Puts"

    message = (
        f"🚨 <b>Options Signal Alert: {ticker}</b> 🚨\n"
        f"Signal: <b>{signal_name} ({signal_type})</b>\n"
        f"Details: {details}\n"
        f"💡 <b>Action:</b> Consider buying {opt_suggestion}."
    )

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in config.TELEGRAM_CHAT_IDS:
        try:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            res = requests.post(url, json=payload, timeout=5)
            res.raise_for_status()
        except Exception as e:
            print(f"Failed to send telegram message to {chat_id}: {e}")
