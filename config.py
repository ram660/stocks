"""
config.py
=========
All user-configurable conditions and thresholds live here.
Edit this file to add, remove, or tweak any signal without touching app logic.
"""

# ---------------------------------------------------------------------------
# Technical-indicator conditions
# Each entry: enabled (bool), signal ("BUY"/"SELL"/"WATCH"), extra params
# ---------------------------------------------------------------------------
CONDITIONS = {
    # RSI
    "RSI Oversold": {
        "enabled": True,
        "description": "RSI below threshold → exhausted sellers → BUY",
        "threshold": 30,
        "signal": "BUY",
        "weight": 2,
    },
    "RSI Overbought": {
        "enabled": True,
        "description": "RSI above threshold → exhausted buyers → SELL",
        "threshold": 70,
        "signal": "SELL",
        "weight": 2,
    },

    # MACD
    "MACD Bullish Crossover": {
        "enabled": True,
        "description": "MACD line crosses above signal line → BUY momentum",
        "signal": "BUY",
        "weight": 2,
    },
    "MACD Bearish Crossover": {
        "enabled": True,
        "description": "MACD line crosses below signal line → SELL momentum",
        "signal": "SELL",
        "weight": 2,
    },

    # Moving averages
    "Golden Cross (50/200 EMA)": {
        "enabled": True,
        "description": "EMA-50 crosses above EMA-200 → long-term uptrend",
        "signal": "BUY",
        "weight": 3,
    },
    "Death Cross (50/200 EMA)": {
        "enabled": True,
        "description": "EMA-50 crosses below EMA-200 → long-term downtrend",
        "signal": "SELL",
        "weight": 3,
    },
    "Price Above EMA 20": {
        "enabled": True,
        "description": "Close > EMA-20 → short-term bullish",
        "signal": "BUY",
        "weight": 1,
    },
    "Price Below EMA 20": {
        "enabled": True,
        "description": "Close < EMA-20 → short-term bearish",
        "signal": "SELL",
        "weight": 1,
    },

    # Bollinger Bands
    "BB Lower Touch": {
        "enabled": True,
        "description": "Price touches/breaks lower Bollinger Band → mean-reversion BUY",
        "signal": "BUY",
        "weight": 1,
    },
    "BB Upper Touch": {
        "enabled": True,
        "description": "Price touches/breaks upper Bollinger Band → mean-reversion SELL",
        "signal": "SELL",
        "weight": 1,
    },
    "BB Squeeze": {
        "enabled": True,
        "description": "Bands narrow (volatility compression) → breakout imminent",
        "signal": "WATCH",
        "weight": 1,
    },

    # VWAP
    "Price Above VWAP": {
        "enabled": True,
        "description": "Close > daily VWAP → institutional buyers in control",
        "signal": "BUY",
        "weight": 1,
    },
    "Price Below VWAP": {
        "enabled": True,
        "description": "Close < daily VWAP → institutional sellers dominating",
        "signal": "SELL",
        "weight": 1,
    },

    # Volume
    "Volume Surge": {
        "enabled": True,
        "description": "Volume > N× average → strong conviction",
        "multiplier": 2.0,
        "signal": "WATCH",
        "weight": 1,
    },

    # Chart patterns
    "Double Bottom": {
        "enabled": True,
        "description": "Two similar lows → reversal BUY pattern",
        "signal": "BUY",
        "weight": 3,
    },
    "Double Top": {
        "enabled": True,
        "description": "Two similar highs → reversal SELL pattern",
        "signal": "SELL",
        "weight": 3,
    },
    "Higher Highs Higher Lows": {
        "enabled": True,
        "description": "Consistent uptrend structure",
        "signal": "BUY",
        "weight": 2,
    },
    "Lower Highs Lower Lows": {
        "enabled": True,
        "description": "Consistent downtrend structure",
        "signal": "SELL",
        "weight": 2,
    },
}

# ---------------------------------------------------------------------------
# EMA periods
# ---------------------------------------------------------------------------
EMA_PERIODS = [9, 20, 50, 200]

# ---------------------------------------------------------------------------
# Bollinger Bands params
# ---------------------------------------------------------------------------
BB_PERIOD   = 20
BB_STDDEV   = 2.0
BB_SQUEEZE_THRESHOLD = 0.05   # bandwidth < 5% of price = squeeze

# ---------------------------------------------------------------------------
# Volume average window (days)
# ---------------------------------------------------------------------------
VOLUME_WINDOW = 20

# ---------------------------------------------------------------------------
# Timeframe presets shown in the UI
# ---------------------------------------------------------------------------
TIMEFRAME_OPTIONS = {
    "1 Day":    {"period": "1d",  "interval": "5m"},
    "5 Days":   {"period": "5d",  "interval": "15m"},
    "1 Month":  {"period": "1mo", "interval": "1h"},
    "3 Months": {"period": "3mo", "interval": "1d"},
    "6 Months": {"period": "6mo", "interval": "1d"},
    "1 Year":   {"period": "1y",  "interval": "1d"},
    "2 Years":  {"period": "2y",  "interval": "1wk"},
}

import os

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
DATA_SOURCE = os.getenv("DATA_SOURCE", "finnhub")   # "yfinance" | "finnhub"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")       # paste your key here if using Finnhub

# ---------------------------------------------------------------------------
# Telegram Alerts Configuration
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") # Enter your bot token here
_ids = os.getenv("TELEGRAM_CHAT_IDS", "744709775")
TELEGRAM_CHAT_IDS = [x.strip() for x in _ids.split(",")]  # List of string chat IDs
