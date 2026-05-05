"""
data_sources.py
===============
Unified data-fetching layer.
Primary: yfinance  (free, no key needed)
Optional: Finnhub  (set FINNHUB_API_KEY in config.py for real-time quotes)
"""
from __future__ import annotations

import time
import streamlit as st
import yfinance as yf
import pandas as pd
import requests

import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def get_history(ticker: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    """Download OHLCV history.  Returns a clean DataFrame or empty."""
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df.empty:
            return pd.DataFrame()
        # Flatten multi-level columns that yfinance sometimes returns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        df = df[~df.index.duplicated(keep="last")]
        return df
    except Exception as e:
        st.warning(f"History fetch error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def get_quote(ticker: str) -> dict:
    """Return real-time/delayed quote dict."""
    if config.DATA_SOURCE == "finnhub" and config.FINNHUB_API_KEY:
        return _finnhub_quote(ticker)
    return _yfinance_quote(ticker)


def _yfinance_quote(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price    = getattr(info, "last_price",  None)
        prev     = getattr(info, "previous_close", None)
        volume   = getattr(info, "three_month_average_volume", None)
        mkt_cap  = getattr(info, "market_cap", None)
        change   = ((price - prev) / prev * 100) if price and prev else 0.0
        return {
            "price":    round(price, 2)   if price   else None,
            "change":   round(change, 2),
            "volume":   int(volume)       if volume  else None,
            "mkt_cap":  mkt_cap,
            "source":   "yfinance",
        }
    except Exception as e:
        return {"price": None, "change": 0, "volume": None, "mkt_cap": None, "error": str(e)}


def _finnhub_quote(ticker: str) -> dict:
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={config.FINNHUB_API_KEY}"
        r = requests.get(url, timeout=5).json()
        price  = r.get("c")
        prev   = r.get("pc")
        change = ((price - prev) / prev * 100) if price and prev else 0.0
        return {
            "price":  round(price, 2) if price else None,
            "change": round(change, 2),
            "volume": None,
            "mkt_cap": None,
            "source": "finnhub",
        }
    except Exception as e:
        return {"price": None, "change": 0, "volume": None, "mkt_cap": None, "error": str(e)}


@st.cache_data(ttl=300, show_spinner=False)
def get_options_chain(ticker: str, expiry: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Fetch options chain.  Returns (calls_df, puts_df, expiry_dates)."""
    try:
        t = yf.Ticker(ticker)
        expiry_dates = list(t.options)
        if not expiry_dates:
            return pd.DataFrame(), pd.DataFrame(), []
        chosen = expiry if expiry in expiry_dates else expiry_dates[0]
        chain = t.option_chain(chosen)
        calls = chain.calls.copy()
        puts  = chain.puts.copy()
        for df in [calls, puts]:
            for col in ["bid", "ask", "lastPrice", "strike", "impliedVolatility",
                        "delta", "gamma", "theta", "vega"]:
                if col not in df.columns:
                    df[col] = None
        return calls, puts, expiry_dates
    except Exception as e:
        st.warning(f"Options fetch error: {e}")
        return pd.DataFrame(), pd.DataFrame(), []


@st.cache_data(ttl=600, show_spinner=False)
def get_fundamentals(ticker: str) -> dict:
    """Fetch key fundamental metrics."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "name":      info.get("longName", ticker),
            "sector":    info.get("sector", "—"),
            "pe":        info.get("trailingPE"),
            "forward_pe":info.get("forwardPE"),
            "beta":      info.get("beta"),
            "52w_high":  info.get("fiftyTwoWeekHigh"),
            "52w_low":   info.get("fiftyTwoWeekLow"),
            "div_yield": info.get("dividendYield"),
            "earnings":  info.get("earningsDate"),
        }
    except Exception:
        return {}
