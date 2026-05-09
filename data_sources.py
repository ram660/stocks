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
    """Download OHLCV history natively switching to Finnhub if configured."""
    if config.DATA_SOURCE == "finnhub" and config.FINNHUB_API_KEY:
        return _finnhub_history(ticker, period, interval)
    return _yfinance_history(ticker, period, interval)

def _yfinance_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
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
        print(f"YFinance History fetch error: {e}")
        return pd.DataFrame()

def _finnhub_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    Fetches real-time candles using Finnhub.
    Resolutions: 1, 5, 15, 30, 60, D, W, M
    """
    try:
        # Match YFinance interval string to Finnhub resolution
        res_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "1d": "D", "1wk": "W", "1mo": "M"}
        resolution = res_map.get(interval, "D")
        
        # Calculate start/end timestamps based on period proxy string
        end_time = int(time.time())
        days_back = 5
        if period == "1mo": days_back = 30
        elif period == "3mo": days_back = 90
        elif period == "6mo": days_back = 180
        elif period == "1y": days_back = 365
        start_time = end_time - (days_back * 24 * 60 * 60)
        
        url = f"https://finnhub.io/api/v1/stock/candle?symbol={ticker}&resolution={resolution}&from={start_time}&to={end_time}&token={config.FINNHUB_API_KEY}"
        r = requests.get(url, timeout=5).json()
        
        if r.get("s") != "ok":
            return pd.DataFrame()
            
        df = pd.DataFrame({
            "Open": r["o"],
            "High": r["h"],
            "Low": r["l"],
            "Close": r["c"],
            "Volume": r["v"]
        })
        # Keep time index format matching YFinance
        df.index = pd.to_datetime(r["t"], unit='s')
        return df
    except Exception as e:
        print(f"Finnhub History fetch error: {e}")
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
