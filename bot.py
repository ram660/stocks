"""
bot.py
======
Headless daemon that monitors tickers (SPY by default) utilizing a dual-timeframe
confluence strategy mapped from the TradingView screenshot.

1-Hour Context: Supertrend, MACD, and DMI.
15-Minute Trigger: Supertrend directional changes.
"""
import time
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify
import sys

import config
import data_sources
import signals as sig_engine
import alerts

app = Flask(__name__)

# Persist state globally in memory while web worker is active
BOT_STATE = {
    "last_15m_dir": None
}

# Announce server startup to Telegram
try:
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_IDS:
        print("Transmitting startup initialization sequence to Telegram...")
        alerts.send_telegram_alert(
            "SYSTEM", 
            "Instance Booted", 
            "ONLINE", 
            "🤖 Headless Options Bot is up and running securely! Live market tracking has commenced."
        )
except Exception as e:
    print(f"Startup alert failed: {e}")

TICKER = "SPY"
POLL_INTERVAL = 60  # seconds

def get_1h_context(df_1h: pd.DataFrame) -> dict:
    """
    Evaluate the 1H timeframe for trend bias context.
    Returns dict with 'bias': 'BULLISH', 'BEARISH', or 'NEUTRAL'
    and 'reasons': list of strings.
    """
    if df_1h.empty:
        return {"bias": "NEUTRAL", "reasons": ["No data"]}

    last_bar = df_1h.iloc[-1]
    
    # 0. ADX Choppiness Filter
    adx_val = last_bar.get("DMI_ADX")
    if pd.notna(adx_val) and adx_val < 20:
        return {"bias": "CHOPPY", "reasons": [f"1H ADX is {adx_val:.1f} (< 20). Market is flat/choppy."]}

    bull_count = 0
    bear_count = 0
    reasons = []

    # 1. Supertrend Context
    st_dir = last_bar.get("Supertrend_Dir", 0)
    if st_dir == 1:
        bull_count += 1
        reasons.append("1H Supertrend is UP")
    elif st_dir == -1:
        bear_count += 1
        reasons.append("1H Supertrend is DOWN")

    # 2. MACD Context
    macd = last_bar.get("MACD")
    macd_signal = last_bar.get("MACD_Signal")
    if pd.notna(macd) and pd.notna(macd_signal):
        if macd > macd_signal:
            bull_count += 1
            reasons.append("1H MACD Bullish")
        elif macd < macd_signal:
            bear_count += 1
            reasons.append("1H MACD Bearish")

    # 3. DMI Context
    plus_di = last_bar.get("DMI_Plus")
    minus_di = last_bar.get("DMI_Minus")
    if pd.notna(plus_di) and pd.notna(minus_di):
        if plus_di > minus_di:
            bull_count += 1
            reasons.append("1H DMI Bullish (+DI > -DI)")
        elif minus_di > plus_di:
            bear_count += 1
            reasons.append("1H DMI Bearish (-DI > +DI)")

    if bull_count == 3:
        bias = "BULLISH"
    elif bear_count == 3:
        bias = "BEARISH"
    else:
        bias = "MIXED"

    return {"bias": bias, "reasons": reasons}

@app.route("/")
def index():
    return jsonify({"status": "running", "ticker": TICKER, "msg": "Headless Bot Webserver."})

@app.route("/check-spy")
def check_spy():
    global BOT_STATE
    print(f"[{datetime.now().strftime('%H:%M:%S')}] PING RECEIVED. Fetching data...")
    try:
        # Fetch data using existing data source functions
        df_1h_raw = data_sources.get_history(TICKER, period="1mo", interval="1h")
        df_15m_raw = data_sources.get_history(TICKER, period="5d", interval="15m")
        
        if df_1h_raw.empty or df_15m_raw.empty:
            return jsonify({"status": "skipped", "reason": "Failed to fetch active data."})
            
        # Process Indicators
        res_1h = sig_engine.run_signals(df_1h_raw)
        df_1h = res_1h["df"]
        
        res_15m = sig_engine.run_signals(df_15m_raw)
        df_15m = res_15m["df"]
        
        if "Supertrend_Dir" not in df_15m.columns:
            return jsonify({"status": "skipped", "reason": "Indicators not computed correctly."})
            
        current_15m_dir = df_15m["Supertrend_Dir"].iloc[-1]
        current_close = df_15m["Close"].iloc[-1]
        current_vol = df_15m["Volume"].iloc[-1]
        vol_avg = df_15m.get("Vol_Avg", pd.Series(dtype=float)).iloc[-1]
        vwap = df_15m.get("VWAP", pd.Series(dtype=float)).iloc[-1]
        st_level = df_15m["Supertrend"].iloc[-1]
        
        # Identify Cross-over event
        last_dir = BOT_STATE["last_15m_dir"]
        
        if last_dir is not None and current_15m_dir != last_dir:
            trigger = "BUY" if current_15m_dir == 1 else "SELL"
            
            # Assess 15-Min Filters
            failed_filters = []
            if trigger == "BUY":
                if pd.notna(vwap) and current_close < vwap:
                    failed_filters.append("Price is below VWAP explicitly fighting institutional flow.")
            elif trigger == "SELL":
                if pd.notna(vwap) and current_close > vwap:
                    failed_filters.append("Price is above VWAP explicitly fighting institutional flow.")

            # Volume Filter
            if pd.notna(vol_avg) and current_vol < vol_avg:
                failed_filters.append(f"Volume ({current_vol:,.0f}) is below the average ({vol_avg:,.0f}). Possible fake-out.")
                
            # Assess 1-Hour Context
            context = get_1h_context(df_1h)
            bias = context["bias"]
            context_str = "\n".join([f"• {r}" for r in context["reasons"]])
            
            details_lines = [
                f"15M Supertrend shifted {trigger} at ${current_close:.2f}.",
                f"Stop Loss Level: <b>${st_level:.2f}</b>\n"
            ]

            if not failed_filters and trigger == "BUY" and bias == "BULLISH":
                details = "\n".join(details_lines) + f"\n<b>1H Confluence (ALL ALIGNED):</b>\n{context_str}"
                print(f"🔥 CONFLUENCE BUY ALERT: {details}")
                alerts.send_telegram_alert(TICKER, "Advanced Dual-Timeframe Strategy", "BUY", details)
                
            elif not failed_filters and trigger == "SELL" and bias == "BEARISH":
                details = "\n".join(details_lines) + f"\n<b>1H Confluence (ALL ALIGNED):</b>\n{context_str}"
                print(f"🔥 CONFLUENCE SELL ALERT: {details}")
                alerts.send_telegram_alert(TICKER, "Advanced Dual-Timeframe Strategy", "SELL", details)
                
            else:                     
                # Mismatched trigger or failed 15m filters
                if failed_filters:
                    fail_str = "\n".join([f"✖ {f}" for f in failed_filters])
                    details = "\n".join(details_lines) + f"\n<b>Failed 15m Requisites:</b>\n{fail_str}\n\n<b>1H State ({bias}):</b>\n{context_str}"
                else:
                    details = "\n".join(details_lines) + f"\n<b>1H State blocked trade ({bias}):</b>\n{context_str}"
                print(f"⚠️ LOW-PROBABILITY ALERT SKIPPED:\n{details}")
                alerts.send_telegram_alert(TICKER, "Skipped Trade (Failed Conditions)", trigger, details)
        
        BOT_STATE["last_15m_dir"] = current_15m_dir
        return jsonify({
            "status": "success",
            "current_close": current_close,
            "15m_dir": int(current_15m_dir)
        })
        
    except Exception as e:
        print(f"Error in webhook loop: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_IDS:
        print("WARNING: Telegram credentials not set tight in config.py! Alerts will only log to console.")
        
    # Standard development server (Waitress/Gunicorn should be used in production)
    app.run(host="0.0.0.0", port=10000)
