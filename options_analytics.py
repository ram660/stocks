"""
options_analytics.py
====================
Advanced options analytics engine.
  - IV Rank / IV Percentile (IVR / IVP)
  - Expected Move (ATM straddle method)
  - Black-Scholes Greeks (pure Python / scipy, no TA-Lib)
  - IV Smile data
  - Options Strategy Scanner + P&L profiles
  - Options Flow analysis
"""
from __future__ import annotations

import math
import datetime
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

try:
    from scipy.stats import norm as _norm
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


# ─────────────────────── Black-Scholes helpers ───────────────────────────────

def _d1(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

def _d2(S, K, T, r, sigma):
    return _d1(S, K, T, r, sigma) - sigma * math.sqrt(T)

def _phi(x):
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def _Phi(x):
    """Standard normal CDF — uses scipy if available, else approximation."""
    if _HAS_SCIPY:
        return float(_norm.cdf(x))
    # Abramowitz & Stegun approximation
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
           t * (-1.821255978 + t * 1.330274429))))
    cdf = 1.0 - _phi(x) * poly
    return cdf if x >= 0 else 1.0 - cdf

def bs_greeks(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str = "call") -> dict:
    """
    Black-Scholes Greeks for a vanilla European option.
    S=spot, K=strike, T=time to expiry (years), r=risk-free rate, sigma=IV
    Returns: delta, gamma, theta (per day), vega (per 1% IV move), rho
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return dict(delta=0, gamma=0, theta=0, vega=0, rho=0, price=0)

    d1 = _d1(S, K, T, r, sigma)
    d2 = _d2(S, K, T, r, sigma)
    sqrtT = math.sqrt(T)
    disc  = math.exp(-r * T)

    gamma = _phi(d1) / (S * sigma * sqrtT)
    vega  = S * _phi(d1) * sqrtT / 100          # per 1% IV move

    if option_type.lower() == "call":
        delta = _Phi(d1)
        theta = (-S * _phi(d1) * sigma / (2 * sqrtT)
                 - r * K * disc * _Phi(d2)) / 365
        rho   = K * T * disc * _Phi(d2) / 100
        price = S * _Phi(d1) - K * disc * _Phi(d2)
    else:
        delta = _Phi(d1) - 1
        theta = (-S * _phi(d1) * sigma / (2 * sqrtT)
                 + r * K * disc * _Phi(-d2)) / 365
        rho   = -K * T * disc * _Phi(-d2) / 100
        price = K * disc * _Phi(-d2) - S * _Phi(d1) + S - K * disc

    return dict(delta=round(delta, 4), gamma=round(gamma, 6),
                theta=round(theta, 4), vega=round(vega, 4),
                rho=round(rho, 4),    price=round(price, 3))


def _days_to_expiry(expiry_str: str) -> float:
    """Return years to expiry from a 'YYYY-MM-DD' string."""
    try:
        exp = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        days  = max((exp - today).days, 1)
        return days / 365.0
    except Exception:
        return 30 / 365.0


# ─────────────────────── IV Rank & IV Percentile ─────────────────────────────

def compute_ivr(ticker: str, current_iv: float | None = None) -> dict:
    """
    Fetch 1-year daily close implied volatility proxy (HV30) and
    compute IV Rank and IV Percentile.

    Because free data doesn't give us historical IV directly, we use
    realised 30-day historical volatility as a proxy and compare current
    ATM IV against its 52-week range.

    Returns: {ivr, ivp, hv_current, iv_52w_high, iv_52w_low, regime}
    """
    try:
        df = yf.download(ticker, period="1y", interval="1d",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].squeeze()

        # 30-day rolling HV
        log_ret = np.log(close / close.shift(1))
        hv30 = log_ret.rolling(21).std() * math.sqrt(252)
        hv30 = hv30.dropna()

        iv_52w_low  = float(hv30.min())
        iv_52w_high = float(hv30.max())
        hv_current  = float(hv30.iloc[-1])

        # If caller passes in actual current IV from chain, use it
        iv_now = current_iv if current_iv else hv_current

        ivr = ((iv_now - iv_52w_low) / (iv_52w_high - iv_52w_low) * 100
               if iv_52w_high > iv_52w_low else 50.0)
        ivp = float((hv30 < iv_now).sum() / len(hv30) * 100)

        if ivr > 50:
            regime = "HIGH"
        elif ivr < 25:
            regime = "LOW"
        else:
            regime = "NEUTRAL"

        return dict(
            ivr=round(ivr, 1),
            ivp=round(ivp, 1),
            hv_current=round(hv_current * 100, 1),
            iv_52w_high=round(iv_52w_high * 100, 1),
            iv_52w_low=round(iv_52w_low * 100, 1),
            iv_now=round(iv_now * 100, 1) if iv_now < 5 else round(iv_now, 1),
            regime=regime,
        )
    except Exception:
        return dict(ivr=50.0, ivp=50.0, hv_current=25.0,
                    iv_52w_high=40.0, iv_52w_low=15.0, iv_now=25.0, regime="NEUTRAL")


# ─────────────────────── Expected Move ───────────────────────────────────────

def expected_move(calls: pd.DataFrame, puts: pd.DataFrame,
                  spot: float, expiry_str: str) -> dict:
    """
    ATM straddle price → 1-SD expected move.
    EM ≈ ATM_call_price + ATM_put_price  (simplified)
    """
    if calls.empty or puts.empty or spot <= 0:
        return {}
    try:
        # Find ATM strike (closest to spot)
        all_strikes = calls["strike"].dropna()
        atm_strike  = all_strikes.iloc[(all_strikes - spot).abs().argsort()[:1]].values[0]

        atm_call = calls[calls["strike"] == atm_strike]["lastPrice"].fillna(0)
        atm_put  = puts[puts["strike"] == atm_strike]["lastPrice"].fillna(0)

        if atm_call.empty or atm_put.empty:
            return {}

        call_price = float(atm_call.iloc[0])
        put_price  = float(atm_put.iloc[0])
        em_dollar  = call_price + put_price
        em_pct     = em_dollar / spot * 100

        days = int(_days_to_expiry(expiry_str) * 365)

        return dict(
            atm_strike=atm_strike,
            call_price=round(call_price, 2),
            put_price=round(put_price, 2),
            em_dollar=round(em_dollar, 2),
            em_pct=round(em_pct, 2),
            upper=round(spot + em_dollar, 2),
            lower=round(spot - em_dollar, 2),
            days=days,
            expiry=expiry_str,
        )
    except Exception:
        return {}


# ─────────────────────── IV Smile Data ───────────────────────────────────────

def iv_smile_data(calls: pd.DataFrame, puts: pd.DataFrame,
                  spot: float) -> pd.DataFrame:
    """
    Build a DataFrame suitable for plotting IV smile/skew.
    Columns: strike, call_iv, put_iv, moneyness
    """
    try:
        call_iv = calls[["strike", "impliedVolatility"]].copy()
        call_iv.columns = ["strike", "call_iv"]
        put_iv  = puts[["strike", "impliedVolatility"]].copy()
        put_iv.columns  = ["strike", "put_iv"]

        merged = pd.merge(call_iv, put_iv, on="strike", how="outer").sort_values("strike")
        merged = merged.dropna(subset=["strike"])
        merged["moneyness"] = merged["strike"] / spot
        merged["call_iv"]   = merged["call_iv"] * 100
        merged["put_iv"]    = merged["put_iv"]  * 100
        return merged.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# ─────────────────────── Greeks Enrichment ───────────────────────────────────

def enrich_greeks(df: pd.DataFrame, spot: float, expiry_str: str,
                  option_type: str = "call", r: float = 0.05) -> pd.DataFrame:
    """
    Compute and append BS Greeks columns for a chain DataFrame.
    Works on raw IV from yfinance (already in decimal, e.g. 0.35 = 35%).
    """
    if df.empty or spot <= 0:
        return df

    T = _days_to_expiry(expiry_str)
    df = df.copy()

    calculated = {k: [] for k in ["bs_delta", "bs_gamma", "bs_theta", "bs_vega", "bs_price"]}

    for _, row in df.iterrows():
        sigma = row.get("impliedVolatility") or 0
        K     = row.get("strike") or 0
        if sigma > 0 and K > 0:
            g = bs_greeks(spot, K, T, r, sigma, option_type)
            calculated["bs_delta"].append(g["delta"])
            calculated["bs_gamma"].append(g["gamma"])
            calculated["bs_theta"].append(g["theta"])
            calculated["bs_vega"].append(g["vega"])
            calculated["bs_price"].append(g["price"])
        else:
            for k in calculated:
                calculated[k].append(None)

    for k, v in calculated.items():
        df[k] = v

    return df


# ─────────────────────── Gamma Exposure (GEX) ────────────────────────────────

def gamma_exposure(calls: pd.DataFrame, puts: pd.DataFrame,
                   spot: float, expiry_str: str) -> pd.DataFrame:
    """
    Estimate dealer gamma exposure per strike.
    GEX = Gamma × OI × 100 × Spot²  (scaled)
    Dealers are short calls → gamma+, short puts → gamma-
    """
    T = _days_to_expiry(expiry_str)
    rows = []
    for _, row in calls.iterrows():
        K  = row.get("strike", 0) or 0
        oi = row.get("openInterest", 0) or 0
        iv = row.get("impliedVolatility", 0) or 0
        if K > 0 and iv > 0:
            g = bs_greeks(spot, K, T, 0.05, iv, "call")["gamma"]
            gex = g * oi * 100 * spot * spot / 1e9  # billions
            rows.append({"strike": K, "gex": gex, "side": "Call"})

    for _, row in puts.iterrows():
        K  = row.get("strike", 0) or 0
        oi = row.get("openInterest", 0) or 0
        iv = row.get("impliedVolatility", 0) or 0
        if K > 0 and iv > 0:
            g = bs_greeks(spot, K, T, 0.05, iv, "put")["gamma"]
            gex = -g * oi * 100 * spot * spot / 1e9  # dealers short puts
            rows.append({"strike": K, "gex": gex, "side": "Put"})

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Net GEX per strike
    net = df.groupby("strike")["gex"].sum().reset_index()
    net.columns = ["strike", "net_gex"]
    net = pd.merge(net, df[df.side == "Call"].rename(columns={"gex": "call_gex"})[["strike", "call_gex"]], on="strike", how="left")
    net = pd.merge(net, df[df.side == "Put"].rename(columns={"gex": "put_gex"})[["strike", "put_gex"]], on="strike", how="left")
    return net.sort_values("strike")


# ─────────────────────── Strategy Scanner ────────────────────────────────────

STRATEGIES = {
    "HIGH": [
        {
            "name": "🦅 Iron Condor",
            "description": "Sell OTM call spread + OTM put spread. Profit if stock stays in range.",
            "legs": ["Sell OTM Call", "Buy further OTM Call", "Sell OTM Put", "Buy further OTM Put"],
            "max_profit": "Net premium collected",
            "max_loss": "Width of spread – premium",
            "ideal": "High IV, range-bound stock",
            "iv_needed": "HIGH",
        },
        {
            "name": "🎯 Short Strangle",
            "description": "Sell OTM call + OTM put. Unlimited risk, collect premium.",
            "legs": ["Sell OTM Call", "Sell OTM Put"],
            "max_profit": "Net premium",
            "max_loss": "Unlimited (call side) / Large (put side)",
            "ideal": "Very high IV, low movement expected",
            "iv_needed": "HIGH",
        },
        {
            "name": "📉 Credit Spread (Bear Call / Bull Put)",
            "description": "Sell closer strike, buy wider strike. Directional with defined risk.",
            "legs": ["Sell ATM/OTM option", "Buy further OTM option"],
            "max_profit": "Net credit",
            "max_loss": "Spread width – credit",
            "ideal": "High IV + directional bias",
            "iv_needed": "HIGH",
        },
        {
            "name": "📞 Covered Call",
            "description": "Own stock + sell OTM call. Generate income, cap upside.",
            "legs": ["Long 100 shares", "Sell OTM Call"],
            "max_profit": "Premium + (strike – cost basis)",
            "max_loss": "Cost basis – premium",
            "ideal": "Own stock, high IV, neutral-to-bullish",
            "iv_needed": "HIGH",
        },
    ],
    "LOW": [
        {
            "name": "🤸 Long Straddle",
            "description": "Buy ATM call + ATM put. Profit from big move in either direction.",
            "legs": ["Buy ATM Call", "Buy ATM Put"],
            "max_profit": "Unlimited",
            "max_loss": "Total premium paid",
            "ideal": "Low IV before catalyst (earnings, FDA, etc.)",
            "iv_needed": "LOW",
        },
        {
            "name": "🚀 Long Call / Long Put",
            "description": "Simple directional bet. Cheap when IV is low.",
            "legs": ["Buy OTM Call (bullish)", "OR Buy OTM Put (bearish)"],
            "max_profit": "Unlimited (call) / Large (put)",
            "max_loss": "Premium paid",
            "ideal": "Strong directional view + low IV",
            "iv_needed": "LOW",
        },
        {
            "name": "📊 Debit Spread",
            "description": "Buy closer strike, sell further strike. Reduces cost, caps profit.",
            "legs": ["Buy ITM/ATM option", "Sell OTM option"],
            "max_profit": "Spread width – debit paid",
            "max_loss": "Debit paid",
            "ideal": "Directional view, low IV, risk-defined",
            "iv_needed": "LOW",
        },
        {
            "name": "📅 Calendar Spread",
            "description": "Buy longer-dated option, sell nearer-dated same strike. Profit from IV rising.",
            "legs": ["Buy far-dated ATM option", "Sell near-dated ATM option"],
            "max_profit": "IV expansion + time decay harvest",
            "max_loss": "Net debit",
            "ideal": "Very low IV, flat price action near-term",
            "iv_needed": "LOW",
        },
    ],
    "NEUTRAL": [
        {
            "name": "💰 Cash-Secured Put",
            "description": "Sell OTM put with cash to buy shares if assigned.",
            "legs": ["Sell OTM Put (secured by cash)"],
            "max_profit": "Premium collected",
            "max_loss": "Strike – premium",
            "ideal": "Want to buy stock cheaper, moderate IV",
            "iv_needed": "NEUTRAL",
        },
        {
            "name": "📐 Butterfly Spread",
            "description": "Buy low, sell 2× mid, buy high. Profit near mid strike.",
            "legs": ["Buy low-strike call", "Sell 2× ATM call", "Buy high-strike call"],
            "max_profit": "Spread width / 2 – debit",
            "max_loss": "Net debit",
            "ideal": "Very neutral, expect pin at middle strike",
            "iv_needed": "NEUTRAL",
        },
    ],
}


def strategy_scan(ivr: float, spot: float,
                  calls: pd.DataFrame, puts: pd.DataFrame,
                  expiry_str: str) -> list[dict]:
    """Return suggested strategies with approximate P&L numbers."""
    if ivr > 50:
        regime = "HIGH"
    elif ivr < 25:
        regime = "LOW"
    else:
        regime = "NEUTRAL"

    base = STRATEGIES.get(regime, [])

    if calls.empty or puts.empty or spot <= 0:
        return base  # return without numbers

    T = _days_to_expiry(expiry_str)
    all_strikes = calls["strike"].dropna().sort_values().values

    # Find ATM and ±5%, ±10% strikes
    def closest(target):
        arr = np.array(all_strikes)
        idx = np.argmin(np.abs(arr - target))
        return arr[idx]

    atm    = closest(spot)
    otm_c5 = closest(spot * 1.05)
    otm_c10= closest(spot * 1.10)
    otm_p5 = closest(spot * 0.95)
    otm_p10= closest(spot * 0.90)

    def get_price(chain, strike):
        row = chain[chain["strike"] == strike]
        if not row.empty:
            p = row["lastPrice"].values[0]
            return round(float(p), 2) if p and not math.isnan(p) else 0.0
        return 0.0

    atm_call  = get_price(calls, atm)
    atm_put   = get_price(puts,  atm)
    otm_c5p   = get_price(calls, otm_c5)
    otm_c10p  = get_price(calls, otm_c10)
    otm_p5p   = get_price(puts,  otm_p5)
    otm_p10p  = get_price(puts,  otm_p10)

    enriched = []
    for s in base:
        s = dict(s)
        name = s["name"]

        if "Iron Condor" in name:
            credit = round((otm_c5p - otm_c10p) + (otm_p5p - otm_p10p), 2)
            width  = round(otm_c10 - otm_c5, 2)
            s["numbers"] = {
                "net_credit": credit,
                "max_profit_$": credit * 100,
                "max_loss_$":   round((width - credit) * 100, 2),
                "breakeven_up": round(otm_c5 + credit, 2),
                "breakeven_dn": round(otm_p5 - credit, 2),
            }
        elif "Strangle" in name:
            credit = round(otm_c5p + otm_p5p, 2)
            s["numbers"] = {
                "net_credit": credit,
                "max_profit_$": credit * 100,
                "max_loss_$": "Unlimited",
                "breakeven_up": round(otm_c5 + credit, 2),
                "breakeven_dn": round(otm_p5 - credit, 2),
            }
        elif "Straddle" in name:
            debit = round(atm_call + atm_put, 2)
            s["numbers"] = {
                "net_debit": debit,
                "max_profit_$": "Unlimited",
                "max_loss_$":   debit * 100,
                "breakeven_up": round(atm + debit, 2),
                "breakeven_dn": round(atm - debit, 2),
            }
        elif "Debit Spread" in name:
            debit = round(atm_call - otm_c5p, 2)
            width = round(otm_c5 - atm, 2)
            s["numbers"] = {
                "net_debit": debit,
                "max_profit_$": round((width - debit) * 100, 2),
                "max_loss_$":   debit * 100,
                "breakeven":    round(atm + debit, 2),
            }
        elif "Cash-Secured Put" in name:
            s["numbers"] = {
                "net_credit": otm_p5p,
                "max_profit_$": otm_p5p * 100,
                "max_loss_$":   round((otm_p5 - otm_p5p) * 100, 2),
                "breakeven":    round(otm_p5 - otm_p5p, 2),
            }

        enriched.append(s)

    return enriched


def pnl_profile(strategy_name: str,
                spot: float, calls: pd.DataFrame, puts: pd.DataFrame,
                expiry_str: str) -> pd.DataFrame:
    """
    Return a DataFrame with columns [price, pnl] for the P&L diagram of a strategy.
    Assumes 1 contract (100 shares).
    """
    all_strikes = calls["strike"].dropna().sort_values().values
    if len(all_strikes) == 0:
        return pd.DataFrame()

    def closest(target):
        arr = np.array(all_strikes)
        return arr[np.argmin(np.abs(arr - target))]

    def get_price(chain, strike):
        row = chain[chain["strike"] == strike]
        if not row.empty:
            p = row["lastPrice"].values[0]
            return float(p) if p and not math.isnan(p) else 0.0
        return 0.0

    atm     = closest(spot)
    otm_c5  = closest(spot * 1.05)
    otm_c10 = closest(spot * 1.10)
    otm_p5  = closest(spot * 0.95)
    otm_p10 = closest(spot * 0.90)

    prices = np.linspace(spot * 0.75, spot * 1.25, 300)

    def call_payoff(K, prem, sign=1):  # sign=+1 long, -1 short
        return sign * (np.maximum(prices - K, 0) - prem) * 100

    def put_payoff(K, prem, sign=1):
        return sign * (np.maximum(K - prices, 0) - prem) * 100

    name = strategy_name.lower()
    pnl = np.zeros(len(prices))

    if "iron condor" in name:
        pnl += call_payoff(otm_c5, get_price(calls, otm_c5), sign=-1)
        pnl += call_payoff(otm_c10, get_price(calls, otm_c10), sign=+1)
        pnl += put_payoff(otm_p5, get_price(puts, otm_p5), sign=-1)
        pnl += put_payoff(otm_p10, get_price(puts, otm_p10), sign=+1)
    elif "strangle" in name:
        pnl += call_payoff(otm_c5, get_price(calls, otm_c5), sign=-1)
        pnl += put_payoff(otm_p5, get_price(puts, otm_p5), sign=-1)
    elif "straddle" in name:
        pnl += call_payoff(atm, get_price(calls, atm), sign=+1)
        pnl += put_payoff(atm, get_price(puts, atm), sign=+1)
    elif "debit spread" in name:
        pnl += call_payoff(atm, get_price(calls, atm), sign=+1)
        pnl += call_payoff(otm_c5, get_price(calls, otm_c5), sign=-1)
    elif "cash-secured put" in name:
        pnl += put_payoff(otm_p5, get_price(puts, otm_p5), sign=-1)
    elif "butterfly" in name:
        pnl += call_payoff(otm_p5, get_price(calls, otm_p5), sign=+1)
        pnl += call_payoff(atm, get_price(calls, atm), sign=-2)
        pnl += call_payoff(otm_c5, get_price(calls, otm_c5), sign=+1)

    return pd.DataFrame({"price": prices, "pnl": pnl})


# ─────────────────────── Options Flow Analysis ───────────────────────────────

def flow_analysis(calls: pd.DataFrame, puts: pd.DataFrame,
                  spot: float) -> dict:
    """
    Build an options flow summary:
    - Top unusual contracts (vol/OI ratio)
    - Bull vs Bear $ premium flow
    - Put/Call volume ratio
    - Put/Call OI ratio
    """
    results = {}

    # Compute $ premium (mid × volume × 100)
    def add_premium(df, side):
        df = df.copy()
        df["mid"] = ((df.get("bid", 0).fillna(0) +
                      df.get("ask", 0).fillna(0)) / 2).clip(lower=0)
        df["premium_$"] = df["mid"] * df["volume"].fillna(0) * 100
        df["vol_oi_ratio"] = (df["volume"].fillna(0) /
                               df["openInterest"].replace(0, np.nan).fillna(np.nan))
        df["side"] = side
        df["itm"] = (df["strike"] < spot) if side == "Call" else (df["strike"] > spot)
        return df

    c = add_premium(calls, "Call") if not calls.empty else pd.DataFrame()
    p = add_premium(puts,  "Put")  if not puts.empty  else pd.DataFrame()

    # Bull ($) = call premium, Bear ($) = put premium
    bull_flow = float(c["premium_$"].sum()) if not c.empty else 0
    bear_flow = float(p["premium_$"].sum()) if not p.empty else 0
    total     = bull_flow + bear_flow
    results["bull_flow_$"]   = round(bull_flow, 0)
    results["bear_flow_$"]   = round(bear_flow, 0)
    results["bull_pct"]      = round(bull_flow / total * 100, 1) if total > 0 else 50.0
    results["bear_pct"]      = round(bear_flow / total * 100, 1) if total > 0 else 50.0
    results["flow_bias"]     = "BULLISH" if bull_flow > bear_flow else "BEARISH"

    # Volume ratios
    call_vol = int(c["volume"].fillna(0).sum()) if not c.empty else 0
    put_vol  = int(p["volume"].fillna(0).sum()) if not p.empty else 0
    call_oi  = int(c["openInterest"].fillna(0).sum()) if not c.empty else 0
    put_oi   = int(p["openInterest"].fillna(0).sum()) if not p.empty else 0

    results["call_vol"]  = call_vol
    results["put_vol"]   = put_vol
    results["pcv_ratio"] = round(put_vol / call_vol, 2) if call_vol else 0
    results["pco_ratio"] = round(put_oi  / call_oi, 2)  if call_oi  else 0

    # Top unusual (vol/OI > 1.5) — potential sweeps / block orders
    all_chain = pd.concat([c, p], ignore_index=True) if not c.empty and not p.empty else pd.DataFrame()
    if not all_chain.empty:
        unusual = all_chain[all_chain["vol_oi_ratio"] > 1.5].copy()
        unusual = unusual.sort_values("vol_oi_ratio", ascending=False).head(10)
        keep = ["strike", "side", "impliedVolatility", "volume",
                "openInterest", "vol_oi_ratio", "premium_$", "itm"]
        keep = [c_ for c_ in keep if c_ in unusual.columns]
        results["top_unusual"] = unusual[keep].reset_index(drop=True)
    else:
        results["top_unusual"] = pd.DataFrame()

    return results
