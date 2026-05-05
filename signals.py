"""
signals.py
==========
Technical conditions & chart-pattern detection engine.
Uses the `ta` library (pandas 2.x compatible).
Returns a list of triggered signals and an overall verdict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import ta

import config


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all indicators in-place and return enriched DataFrame."""
    close = df["Close"].squeeze()
    high  = df["High"].squeeze()
    low   = df["Low"].squeeze()
    vol   = df["Volume"].squeeze()

    # EMAs
    for p in config.EMA_PERIODS:
        df[f"EMA_{p}"] = ta.trend.ema_indicator(close, window=p)

    # MACD
    macd_ind = ta.trend.MACD(close)
    df["MACD"]        = macd_ind.macd()
    df["MACD_Signal"] = macd_ind.macd_signal()
    df["MACD_Hist"]   = macd_ind.macd_diff()

    # RSI
    df["RSI"] = ta.momentum.rsi(close, window=14)

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(close, window=config.BB_PERIOD, window_dev=config.BB_STDDEV)
    df["BB_Upper"] = bb.bollinger_hband()
    df["BB_Mid"]   = bb.bollinger_mavg()
    df["BB_Lower"] = bb.bollinger_lband()
    df["BB_BWidth"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Mid"]

    # VWAP (rolling approximation for multi-day charts)
    typical = (high + low + close) / 3
    df["VWAP"] = (typical * vol).cumsum() / vol.cumsum()

    # Volume moving average
    df["Vol_Avg"] = vol.rolling(config.VOLUME_WINDOW).mean()

    return df


def _safe_last(series, n: int = 1):
    """Return the last n valid scalar(s) from a series."""
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    clean = series.dropna()
    if len(clean) < n:
        return [None] * n
    return [float(v) for v in clean.iloc[-n:].tolist()]


# ---------------------------------------------------------------------------
# Individual condition checks — each returns dict or None
# ---------------------------------------------------------------------------

def _check_rsi(df, cond_name, cfg) -> dict | None:
    rsi_vals = _safe_last(df["RSI"])
    rsi = rsi_vals[0]
    if rsi is None:
        return None
    thr = cfg["threshold"]
    if cfg["signal"] == "BUY"  and rsi < thr:
        return {"name": cond_name, "signal": "BUY",  "value": round(rsi, 1), "note": f"RSI={rsi:.1f} < {thr}"}
    if cfg["signal"] == "SELL" and rsi > thr:
        return {"name": cond_name, "signal": "SELL", "value": round(rsi, 1), "note": f"RSI={rsi:.1f} > {thr}"}
    return None


def _check_macd(df, cond_name, cfg) -> dict | None:
    if "MACD" not in df.columns:
        return None
    macd   = _safe_last(df["MACD"], 2)
    signal = _safe_last(df["MACD_Signal"], 2)
    if None in macd or None in signal:
        return None
    prev_above = macd[0] > signal[0]
    curr_above = macd[1] > signal[1]
    if cfg["signal"] == "BUY"  and not prev_above and curr_above:
        return {"name": cond_name, "signal": "BUY",  "value": round(macd[1], 3), "note": "MACD crossed above signal"}
    if cfg["signal"] == "SELL" and prev_above and not curr_above:
        return {"name": cond_name, "signal": "SELL", "value": round(macd[1], 3), "note": "MACD crossed below signal"}
    return None


def _check_ema_cross(df, cond_name, cfg) -> dict | None:
    col50  = df.get("EMA_50",  pd.Series(dtype=float))
    col200 = df.get("EMA_200", pd.Series(dtype=float))
    if isinstance(col50, pd.DataFrame):  col50  = col50.iloc[:, 0]
    if isinstance(col200, pd.DataFrame): col200 = col200.iloc[:, 0]
    e50  = _safe_last(col50,  2)
    e200 = _safe_last(col200, 2)
    if None in e50 or None in e200:
        return None
    prev_golden = e50[0] > e200[0]
    curr_golden = e50[1] > e200[1]
    if cfg["signal"] == "BUY"  and not prev_golden and curr_golden:
        return {"name": cond_name, "signal": "BUY",  "value": round(e50[1], 2), "note": "EMA50 crossed above EMA200"}
    if cfg["signal"] == "SELL" and prev_golden and not curr_golden:
        return {"name": cond_name, "signal": "SELL", "value": round(e50[1], 2), "note": "EMA50 crossed below EMA200"}
    return None


def _check_price_ema20(df, cond_name, cfg) -> dict | None:
    col20 = df.get("EMA_20", pd.Series(dtype=float))
    if isinstance(col20, pd.DataFrame): col20 = col20.iloc[:, 0]
    ema20 = _safe_last(col20)
    close = _safe_last(df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"])
    if None in ema20 or None in close:
        return None
    if cfg["signal"] == "BUY"  and close[0] > ema20[0]:
        return {"name": cond_name, "signal": "BUY",  "value": round(close[0], 2), "note": f"Close={close[0]:.2f} > EMA20={ema20[0]:.2f}"}
    if cfg["signal"] == "SELL" and close[0] < ema20[0]:
        return {"name": cond_name, "signal": "SELL", "value": round(close[0], 2), "note": f"Close={close[0]:.2f} < EMA20={ema20[0]:.2f}"}
    return None


def _check_bb(df, cond_name, cfg) -> dict | None:
    if "BB_Lower" not in df.columns:
        return None
    close_s = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    close = _safe_last(close_s)
    lower = _safe_last(df["BB_Lower"])
    upper = _safe_last(df["BB_Upper"])
    bw    = _safe_last(df["BB_BWidth"])
    if None in close or None in lower or None in upper:
        return None
    if cfg["signal"] == "BUY"  and close[0] <= lower[0]:
        return {"name": cond_name, "signal": "BUY",  "value": round(close[0], 2), "note": "Price at/below lower Bollinger Band"}
    if cfg["signal"] == "SELL" and close[0] >= upper[0]:
        return {"name": cond_name, "signal": "SELL", "value": round(close[0], 2), "note": "Price at/above upper Bollinger Band"}
    if cfg["signal"] == "WATCH" and bw[0] is not None and bw[0] < config.BB_SQUEEZE_THRESHOLD:
        return {"name": cond_name, "signal": "WATCH", "value": round(bw[0], 4), "note": f"BB bandwidth={bw[0]:.4f} (squeeze)"}
    return None


def _check_vwap(df, cond_name, cfg) -> dict | None:
    vwap  = _safe_last(df["VWAP"])
    close_s = df["Close"].squeeze() if isinstance(df["Close"], pd.DataFrame) else df["Close"]
    close = _safe_last(close_s)
    if None in vwap or None in close:
        return None
    if cfg["signal"] == "BUY"  and close[0] > vwap[0]:
        return {"name": cond_name, "signal": "BUY",  "value": round(close[0], 2), "note": f"Close above VWAP ({vwap[0]:.2f})"}
    if cfg["signal"] == "SELL" and close[0] < vwap[0]:
        return {"name": cond_name, "signal": "SELL", "value": round(close[0], 2), "note": f"Close below VWAP ({vwap[0]:.2f})"}
    return None


def _check_volume_surge(df, cond_name, cfg) -> dict | None:
    vol_s = df["Volume"].squeeze() if isinstance(df["Volume"], pd.DataFrame) else df["Volume"]
    vol     = _safe_last(vol_s)
    vol_avg = _safe_last(df["Vol_Avg"])
    if None in vol or None in vol_avg or vol_avg[0] == 0:
        return None
    ratio = vol[0] / vol_avg[0]
    if ratio >= cfg["multiplier"]:
        return {"name": cond_name, "signal": "WATCH", "value": round(ratio, 2), "note": f"Volume {ratio:.1f}× the 20-day average"}
    return None


def _check_double_bottom(df, cond_name, cfg) -> dict | None:
    if len(df) < 30:
        return None
    low_s = df["Low"].squeeze() if isinstance(df["Low"], pd.DataFrame) else df["Low"]
    lows = low_s.values[-60:]
    minima = [(i, lows[i]) for i in range(1, len(lows)-1)
              if lows[i] < lows[i-1] and lows[i] < lows[i+1]]
    for i in range(len(minima)):
        for j in range(i+1, len(minima)):
            idx1, v1 = minima[i]; idx2, v2 = minima[j]
            if abs(idx2-idx1) >= 10 and v1 > 0 and abs(v1-v2)/v1 < 0.01:
                return {"name": cond_name, "signal": "BUY", "value": round(v1, 2), "note": "Double bottom detected"}
    return None


def _check_double_top(df, cond_name, cfg) -> dict | None:
    if len(df) < 30:
        return None
    high_s = df["High"].squeeze() if isinstance(df["High"], pd.DataFrame) else df["High"]
    highs = high_s.values[-60:]
    maxima = [(i, highs[i]) for i in range(1, len(highs)-1)
              if highs[i] > highs[i-1] and highs[i] > highs[i+1]]
    for i in range(len(maxima)):
        for j in range(i+1, len(maxima)):
            idx1, v1 = maxima[i]; idx2, v2 = maxima[j]
            if abs(idx2-idx1) >= 10 and v1 > 0 and abs(v1-v2)/v1 < 0.01:
                return {"name": cond_name, "signal": "SELL", "value": round(v1, 2), "note": "Double top detected"}
    return None


def _check_hh_hl(df, cond_name, cfg) -> dict | None:
    if len(df) < 20:
        return None
    sub = df.tail(20)
    highs = sub["High"].squeeze().values if isinstance(sub["High"], pd.DataFrame) else sub["High"].values
    lows  = sub["Low"].squeeze().values  if isinstance(sub["Low"],  pd.DataFrame) else sub["Low"].values
    if highs[-1] > highs[0] and lows[-1] > lows[0]:
        return {"name": cond_name, "signal": "BUY", "value": None, "note": "Uptrend: higher highs + higher lows"}
    return None


def _check_lh_ll(df, cond_name, cfg) -> dict | None:
    if len(df) < 20:
        return None
    sub = df.tail(20)
    highs = sub["High"].squeeze().values if isinstance(sub["High"], pd.DataFrame) else sub["High"].values
    lows  = sub["Low"].squeeze().values  if isinstance(sub["Low"],  pd.DataFrame) else sub["Low"].values
    if highs[-1] < highs[0] and lows[-1] < lows[0]:
        return {"name": cond_name, "signal": "SELL", "value": None, "note": "Downtrend: lower highs + lower lows"}
    return None


# ---------------------------------------------------------------------------
# Dispatcher map
# ---------------------------------------------------------------------------

CHECKERS = {
    "RSI Oversold":                _check_rsi,
    "RSI Overbought":              _check_rsi,
    "MACD Bullish Crossover":      _check_macd,
    "MACD Bearish Crossover":      _check_macd,
    "Golden Cross (50/200 EMA)":   _check_ema_cross,
    "Death Cross (50/200 EMA)":    _check_ema_cross,
    "Price Above EMA 20":          _check_price_ema20,
    "Price Below EMA 20":          _check_price_ema20,
    "BB Lower Touch":              _check_bb,
    "BB Upper Touch":              _check_bb,
    "BB Squeeze":                  _check_bb,
    "Price Above VWAP":            _check_vwap,
    "Price Below VWAP":            _check_vwap,
    "Volume Surge":                _check_volume_surge,
    "Double Bottom":               _check_double_bottom,
    "Double Top":                  _check_double_top,
    "Higher Highs Higher Lows":    _check_hh_hl,
    "Lower Highs Lower Lows":      _check_lh_ll,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_signals(df: pd.DataFrame, active_conditions: dict | None = None) -> dict:
    """
    Run all enabled conditions against OHLCV DataFrame.
    Returns verdict, score, triggered signals list, and enriched df.
    """
    if df.empty or len(df) < 5:
        return {"verdict": "NO DATA", "score": 0, "signals": [], "df": df}

    df = _add_indicators(df.copy())
    conditions = config.CONDITIONS
    if active_conditions:
        conditions = {k: {**v, "enabled": active_conditions.get(k, v["enabled"])}
                      for k, v in conditions.items()}

    triggered = []
    score = 0

    for name, cfg in conditions.items():
        if not cfg.get("enabled", True):
            continue
        checker = CHECKERS.get(name)
        if checker is None:
            continue
        try:
            result = checker(df, name, cfg)
        except Exception:
            result = None
        if result:
            result["weight"] = cfg.get("weight", 1)
            triggered.append(result)
            if result["signal"] == "BUY":
                score += cfg.get("weight", 1)
            elif result["signal"] == "SELL":
                score -= cfg.get("weight", 1)

    if score >= 3:
        verdict = "BUY"
    elif score <= -3:
        verdict = "SELL"
    elif score == 0 and any(s["signal"] == "WATCH" for s in triggered):
        verdict = "WATCH"
    else:
        verdict = "HOLD"

    return {"verdict": verdict, "score": score, "signals": triggered, "df": df}
