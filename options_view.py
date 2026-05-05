"""
options_view.py  (v2 — Advanced Options Dashboard)
===================================================
5 sub-tabs:
  📊 Overview    — IVR gauge, expected move, strategy recommendation
  📋 Chain       — full options chain with BS Greeks
  📉 IV Smile    — IV skew chart
  🔥 Greeks      — Greeks heatmap + GEX
  ⚡ Flow        — unusual activity + bull/bear $ flow
"""
from __future__ import annotations

import math
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import data_sources
import options_analytics as oa

# ─── Dark-theme colour constants ─────────────────────────────────────────────
BG     = "#0e1117"
PANEL  = "#161b22"
GREEN  = "#00c853"
RED    = "#ff1744"
YELLOW = "#ffd600"
BLUE   = "#448aff"
WHITE  = "#e6edf3"
MUTED  = "#8b949e"


# ─── Small helpers ────────────────────────────────────────────────────────────

def _dark_fig(height=320):
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color=WHITE, family="Inter, sans-serif"),
        height=height, margin=dict(l=8, r=8, t=30, b=8),
        xaxis=dict(gridcolor="#21262d", zeroline=False),
        yaxis=dict(gridcolor="#21262d", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0.4)", bordercolor=MUTED,
                    borderwidth=1, orientation="h", y=-0.25),
    )
    return fig

def _fmt_iv(x):
    try:
        v = float(x)
        return f"{v:.1%}"
    except Exception:
        return "—"

def _fmt(x, decimals=2):
    try:
        return round(float(x), decimals)
    except Exception:
        return "—"

def _ivr_color(ivr: float) -> str:
    if ivr >= 60:   return RED
    if ivr >= 35:   return YELLOW
    return GREEN

def _regime_desc(regime: str) -> str:
    return {
        "HIGH":    "🔴 High IV — favour **selling** premium (Iron Condor, Strangle, Credit Spread)",
        "LOW":     "🟢 Low IV  — favour **buying** premium (Straddle, Long Call/Put, Debit Spread)",
        "NEUTRAL": "🟡 Neutral — balanced strategies (Covered Call, Cash-Secured Put, Butterfly)",
    }.get(regime, "")


# ─── IVR Gauge ───────────────────────────────────────────────────────────────

def _ivr_gauge(ivr: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=ivr,
        number={"suffix": "%", "font": {"size": 36, "color": WHITE}},
        title={"text": "IV Rank (IVR)", "font": {"color": MUTED, "size": 13}},
        gauge={
            "axis":  {"range": [0, 100], "tickcolor": MUTED},
            "bar":   {"color": _ivr_color(ivr)},
            "bgcolor": PANEL,
            "bordercolor": "#21262d",
            "steps": [
                {"range": [0,  25], "color": "rgba(0,200,83,0.12)"},
                {"range": [25, 50], "color": "rgba(255,214,0,0.12)"},
                {"range": [50,100], "color": "rgba(255,23,68,0.12)"},
            ],
            "threshold": {"line": {"color": WHITE, "width": 2}, "value": ivr},
        },
    ))
    fig.update_layout(
        paper_bgcolor=BG,
        font=dict(color=WHITE),
        height=220, margin=dict(l=20, r=20, t=20, b=10),
    )
    return fig


# ─── P&L Diagram ─────────────────────────────────────────────────────────────

def _pnl_chart(pnl_df: pd.DataFrame, strategy_name: str,
               spot: float) -> go.Figure:
    if pnl_df.empty:
        return None
    fig = _dark_fig(height=280)
    colors = [GREEN if v >= 0 else RED for v in pnl_df["pnl"]]
    fig.add_trace(go.Scatter(
        x=pnl_df["price"], y=pnl_df["pnl"],
        fill="tozeroy",
        fillcolor="rgba(0,200,83,0.1)",
        line=dict(color=GREEN, width=2),
        name="P&L at Expiry ($)",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=MUTED, line_width=1)
    fig.add_vline(x=spot, line_dash="dot", line_color=YELLOW, line_width=1,
                  annotation_text=f"Spot ${spot:.2f}", annotation_font_color=YELLOW)
    fig.update_layout(
        title=dict(text=f"P&L Diagram — {strategy_name}", font=dict(size=13)),
        xaxis_title="Stock Price at Expiry",
        yaxis_title="P&L ($)",
    )
    return fig


# ─── Greeks Heatmap ──────────────────────────────────────────────────────────

def _greeks_table(calls: pd.DataFrame, puts: pd.DataFrame) -> tuple[go.Figure | None, go.Figure | None]:
    """Side-by-side calls + puts Greeks tables — returned as two separate figures."""
    needed = ["strike", "bs_delta", "bs_gamma", "bs_theta", "bs_vega"]

    def prep(df):
        cols = [c for c in needed if c in df.columns]
        d = df[cols].head(20).copy()
        d.columns = [c.replace("bs_", "") for c in cols]
        return d

    c = prep(calls) if not calls.empty and "bs_delta" in calls.columns else pd.DataFrame()
    p = prep(puts)  if not puts.empty  and "bs_delta" in puts.columns  else pd.DataFrame()

    def make_table_fig(df, title):
        if df.empty:
            return None
        # Build fill colours per column
        fill_colors = []
        for col_name in df.columns:
            vals = df[col_name].fillna(0)
            if col_name == "gamma":
                maxg = vals.abs().max() or 1
                clrs = [f"rgba(68,138,255,{min(abs(v)/maxg, 1):.2f})" for v in vals]
            elif col_name == "delta":
                clrs = [
                    f"rgba(0,200,83,{min(abs(v), 1):.2f})" if v >= 0
                    else f"rgba(255,23,68,{min(abs(v), 1):.2f})"
                    for v in vals
                ]
            elif col_name == "theta":
                clrs = [f"rgba(255,23,68,{min(abs(v)*10, 0.6):.2f})" for v in vals]
            else:
                clrs = [PANEL] * len(df)
            fill_colors.append(clrs)

        fig = go.Figure(go.Table(
            header=dict(
                values=[f"<b>{c.title()}</b>" for c in df.columns],
                fill_color="#21262d",
                font=dict(color=WHITE, size=11),
                align="center",
            ),
            cells=dict(
                values=[df[c].round(4).tolist() for c in df.columns],
                fill_color=fill_colors,
                font=dict(color=WHITE, size=10),
                align="center",
            ),
        ))
        fig.update_layout(
            paper_bgcolor=BG,
            font=dict(color=WHITE),
            height=420,
            margin=dict(l=5, r=5, t=30, b=5),
            title=dict(text=title, font=dict(size=13, color=WHITE)),
        )
        return fig

    return make_table_fig(c, "📗 Calls Greeks"), make_table_fig(p, "📕 Puts Greeks")


# ─── Gamma Exposure Chart ────────────────────────────────────────────────────

def _gex_chart(gex_df: pd.DataFrame, spot: float) -> go.Figure:
    if gex_df.empty:
        return None
    fig = _dark_fig(height=280)
    fig.add_trace(go.Bar(
        x=gex_df["strike"],
        y=gex_df["net_gex"],
        marker_color=[GREEN if v >= 0 else RED for v in gex_df["net_gex"]],
        name="Net GEX (B$)",
    ))
    fig.add_vline(x=spot, line_dash="dot", line_color=YELLOW,
                  annotation_text=f"Spot ${spot:.0f}",
                  annotation_font_color=YELLOW)
    flip_point = gex_df.iloc[(gex_df["net_gex"]).abs().argsort()[:1]]["strike"].values
    if len(flip_point):
        fig.add_vline(x=flip_point[0], line_dash="dash", line_color=BLUE,
                      annotation_text="Gamma Flip", annotation_font_color=BLUE)
    fig.update_layout(
        title=dict(text="Dealer Gamma Exposure (GEX) by Strike", font=dict(size=13)),
        xaxis_title="Strike", yaxis_title="Net GEX (Billions $)",
    )
    return fig


# ─── IV Smile Chart ──────────────────────────────────────────────────────────

def _smile_chart(smile_df: pd.DataFrame, spot: float) -> go.Figure:
    if smile_df.empty:
        return None
    fig = _dark_fig(height=300)
    if "call_iv" in smile_df.columns:
        fig.add_trace(go.Scatter(
            x=smile_df["strike"], y=smile_df["call_iv"],
            line=dict(color=GREEN, width=2), name="Call IV %",
            mode="lines+markers", marker=dict(size=5),
        ))
    if "put_iv" in smile_df.columns:
        fig.add_trace(go.Scatter(
            x=smile_df["strike"], y=smile_df["put_iv"],
            line=dict(color=RED, width=2), name="Put IV %",
            mode="lines+markers", marker=dict(size=5),
        ))
    fig.add_vline(x=spot, line_dash="dot", line_color=YELLOW,
                  annotation_text=f"ATM ${spot:.2f}",
                  annotation_font_color=YELLOW)
    fig.update_layout(
        title=dict(text="IV Smile / Skew", font=dict(size=13)),
        xaxis_title="Strike", yaxis_title="Implied Volatility (%)",
    )
    return fig


# ─── Flow Bar ────────────────────────────────────────────────────────────────

def _flow_bar(bull_pct: float, bear_pct: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["$ Flow"], x=[bull_pct], orientation="h",
        name="Bull (Calls)", marker_color=GREEN,
        text=[f"🟢 {bull_pct:.1f}%"], textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["$ Flow"], x=[bear_pct], orientation="h",
        name="Bear (Puts)", marker_color=RED,
        text=[f"🔴 {bear_pct:.1f}%"], textposition="inside",
    ))
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color=WHITE), barmode="stack",
        height=80, margin=dict(l=5, r=5, t=5, b=5),
        showlegend=False,
        xaxis=dict(range=[0, 100], showgrid=False, showticklabels=False),
        yaxis=dict(showgrid=False),
    )
    return fig


# ─── Main Render Function ────────────────────────────────────────────────────

def render_options(ticker: str, spot: float = 0.0):
    """Render the full advanced options dashboard."""

    calls_raw, puts_raw, expiries = data_sources.get_options_chain(ticker)

    if not expiries:
        st.warning("⚠️ No options data available for this ticker.")
        return

    # ── Shared expiry selector (top-level, above sub-tabs) ─────────────────
    col_exp, col_dte = st.columns([3, 1])
    with col_exp:
        chosen_expiry = st.selectbox("📅 Expiration", expiries, key="opts_expiry_v2")
    calls, puts, _ = data_sources.get_options_chain(ticker, chosen_expiry)
    import datetime
    try:
        exp_dt  = datetime.datetime.strptime(chosen_expiry, "%Y-%m-%d").date()
        dte     = max((exp_dt - datetime.date.today()).days, 0)
    except Exception:
        dte = "—"
    with col_dte:
        st.metric("📆 DTE", f"{dte} days")

    if spot <= 0 and not calls.empty:
        spot_val = float(calls["strike"].median())
    else:
        spot_val = spot

    # ── Sub-tabs ───────────────────────────────────────────────────────────
    t_overview, t_chain, t_smile, t_greeks, t_flow = st.tabs([
        "📊 Overview", "📋 Chain", "📉 IV Smile", "🔥 Greeks & GEX", "⚡ Flow"
    ])


    # ══════════════════════════ TAB: OVERVIEW ══════════════════════════════
    with t_overview:
        # Compute IVR using ATM IV as current IV
        atm_iv = None
        if not calls.empty:
            all_strikes = calls["strike"].dropna()
            atm_s = all_strikes.iloc[(all_strikes - spot_val).abs().argsort()[:1]]
            if not atm_s.empty:
                atm_row = calls[calls["strike"] == atm_s.values[0]]
                if not atm_row.empty:
                    atm_iv = atm_row["impliedVolatility"].values[0]

        with st.spinner("Computing IV Rank…"):
            iv_data = oa.compute_ivr(ticker, current_iv=atm_iv)

        # ── Row 1: IVR gauge + key metrics ──────────────────────────────
        g_col, m_col = st.columns([1.4, 2])
        with g_col:
            st.plotly_chart(_ivr_gauge(iv_data["ivr"]),
                            use_container_width=True, key="ivr_gauge")
        with m_col:
            st.markdown(f"#### Volatility Environment: {_regime_desc(iv_data['regime'])}")
            st.markdown("---")
            r1, r2, r3 = st.columns(3)
            r1.metric("IVR",  f"{iv_data['ivr']:.1f}%",
                      help="IV Rank: 0=cheapest, 100=most expensive in 52w")
            r2.metric("IVP",  f"{iv_data['ivp']:.1f}%",
                      help="IV Percentile: % of days IV was below current level")
            r3.metric("HV 30d", f"{iv_data['hv_current']:.1f}%",
                      help="30-day realised historical volatility (annualised)")
            r4, r5, _ = st.columns(3)
            r4.metric("52w IV High", f"{iv_data['iv_52w_high']:.1f}%")
            r5.metric("52w IV Low",  f"{iv_data['iv_52w_low']:.1f}%")

        st.markdown("---")

        # ── Expected Move ────────────────────────────────────────────────
        em = oa.expected_move(calls, puts, spot_val, chosen_expiry)
        if em:
            st.markdown("#### 📐 Expected Move (ATM Straddle Method)")
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("± $ Move", f"${em['em_dollar']:.2f}", help="ATM Call + ATM Put price")
            e2.metric("± % Move", f"{em['em_pct']:.2f}%")
            e3.metric("Upper bound", f"${em['upper']:.2f}", delta="by expiry", delta_color="off")
            e4.metric("Lower bound", f"${em['lower']:.2f}", delta="by expiry", delta_color="off")
            st.caption(f"ATM strike: ${em['atm_strike']:.2f} | "
                       f"Call: ${em['call_price']:.2f} + Put: ${em['put_price']:.2f} = "
                       f"${em['em_dollar']:.2f} in {em['days']} days")

        st.markdown("---")

        # ── Strategy recommendations ──────────────────────────────────────
        st.markdown("#### 🧠 Strategy Recommendations")
        with st.spinner("Scanning strategies…"):
            strategies = oa.strategy_scan(iv_data["ivr"], spot_val, calls, puts, chosen_expiry)

        for strat in strategies[:3]:
            with st.expander(f"**{strat['name']}** — {strat['description']}", expanded=False):
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"**Legs:** {' · '.join(strat['legs'])}")
                    st.markdown(f"**Max Profit:** {strat['max_profit']}")
                    st.markdown(f"**Max Loss:** {strat['max_loss']}")
                    st.markdown(f"**Ideal for:** {strat['ideal']}")
                    if "numbers" in strat:
                        st.markdown("**Live numbers (1 contract):**")
                        for k, v in strat["numbers"].items():
                            label = k.replace("_", " ").title()
                            val   = f"${v:,.2f}" if isinstance(v, float) else str(v)
                            st.markdown(f"- {label}: **{val}**")
                with c2:
                    pnl_df = oa.pnl_profile(strat["name"], spot_val, calls, puts, chosen_expiry)
                    fig    = _pnl_chart(pnl_df, strat["name"], spot_val)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True,
                                        key=f"pnl_{strat['name'][:8]}")


    # ══════════════════════════ TAB: CHAIN ══════════════════════════════════
    with t_chain:
        # ── Summary metrics ──────────────────────────────────────────────
        call_oi = int(calls["openInterest"].fillna(0).sum()) if not calls.empty else 0
        put_oi  = int(puts["openInterest"].fillna(0).sum())  if not puts.empty  else 0
        pcr = round(put_oi / call_oi, 2) if call_oi else None
        mp  = _max_pain(calls, puts)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Put/Call OI Ratio", f"{pcr:.2f}" if pcr else "—",
                  delta="Bearish" if pcr and pcr > 1 else "Bullish")
        m2.metric("🎯 Max Pain", f"${mp:.2f}" if mp else "—")
        m3.metric("Call OI", f"{call_oi:,}")
        m4.metric("Put OI",  f"{put_oi:,}")

        st.markdown("---")
        show_greeks = st.checkbox("Show BS Greeks columns", value=True, key="chain_greeks")

        # Enrich with BS Greeks
        if show_greeks and spot_val > 0:
            with st.spinner("Computing Greeks…"):
                calls_rich = oa.enrich_greeks(calls, spot_val, chosen_expiry, "call")
                puts_rich  = oa.enrich_greeks(puts,  spot_val, chosen_expiry, "put")
        else:
            calls_rich = calls.copy()
            puts_rich  = puts.copy()

        # Flag unusual
        calls_rich = _flag_unusual(calls_rich)
        puts_rich  = _flag_unusual(puts_rich)

        base_cols = ["strike", "lastPrice", "bid", "ask", "volume",
                     "openInterest", "impliedVolatility", "⚡"]
        greek_cols = ["bs_delta", "bs_gamma", "bs_theta", "bs_vega"]
        show_cols = base_cols + (greek_cols if show_greeks else [])

        rename = {"openInterest": "OI", "impliedVolatility": "IV",
                  "lastPrice": "Last", "strike": "Strike",
                  "bs_delta": "Δ Delta", "bs_gamma": "Γ Gamma",
                  "bs_theta": "Θ Theta", "bs_vega": "V Vega"}

        def present_chain(df, label):
            st.markdown(f"#### {label}")
            if df.empty:
                st.info(f"No {label} data.")
                return
            df = df.copy()
            if "impliedVolatility" in df.columns:
                df["impliedVolatility"] = df["impliedVolatility"].apply(_fmt_iv)
            cols = [c for c in show_cols if c in df.columns]
            out  = df[cols].rename(columns=rename)
            st.dataframe(out, use_container_width=True, height=320, hide_index=True)

        present_chain(calls_rich, "📗 Calls")
        present_chain(puts_rich,  "📕 Puts")

        # OI chart
        st.markdown("#### Open Interest by Strike")
        _oi_chart(calls_rich, puts_rich, mp, spot_val)


    # ══════════════════════════ TAB: IV SMILE ═══════════════════════════════
    with t_smile:
        st.markdown("#### 📉 Implied Volatility Smile / Skew")
        st.caption("This chart shows IV across strikes. A steep left skew = market fears downside. "
                   "A right skew = gamma squeeze risk to the upside.")

        smile_df = oa.iv_smile_data(calls, puts, spot_val)
        fig = _smile_chart(smile_df, spot_val)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key="smile_chart")
        else:
            st.info("Could not compute IV smile from current chain data.")

        if not smile_df.empty:
            # Skew metric: 25Δ put IV – 25Δ call IV (approximated by OTM strikes)
            try:
                otm_put_iv  = smile_df[smile_df["moneyness"] < 0.97]["put_iv"].mean()
                otm_call_iv = smile_df[smile_df["moneyness"] > 1.03]["call_iv"].mean()
                skew = round(otm_put_iv - otm_call_iv, 1) if otm_put_iv and otm_call_iv else None
                s1, s2, s3 = st.columns(3)
                s1.metric("OTM Put IV (avg)", f"{otm_put_iv:.1f}%" if otm_put_iv else "—")
                s2.metric("OTM Call IV (avg)", f"{otm_call_iv:.1f}%" if otm_call_iv else "—")
                if skew:
                    s3.metric("Skew (put–call)", f"{skew:+.1f}%",
                              delta="Bearish skew" if skew > 0 else "Bullish skew",
                              delta_color="inverse" if skew > 0 else "normal")
            except Exception:
                pass


    # ══════════════════════════ TAB: GREEKS & GEX ═══════════════════════════
    with t_greeks:
        st.markdown("#### 🔥 Greeks Heatmap")
        st.caption("Delta: directional exposure · Gamma: rate-of-delta-change (key for MMs) · "
                   "Theta: daily decay · Vega: IV sensitivity")

        if spot_val > 0:
            with st.spinner("Computing BS Greeks for all strikes…"):
                c_g = oa.enrich_greeks(calls, spot_val, chosen_expiry, "call")
                p_g = oa.enrich_greeks(puts,  spot_val, chosen_expiry, "put")
        else:
            c_g = calls.copy(); p_g = puts.copy()

        fig_c, fig_p = _greeks_table(c_g, p_g)
        if fig_c and fig_p:
            st.plotly_chart(fig_c, use_container_width=True, key="greeks_calls")
            st.plotly_chart(fig_p, use_container_width=True, key="greeks_puts")
        else:
            st.info("Greeks require strike + IV data. Try a different expiry.")

        st.markdown("---")
        st.markdown("#### 📊 Dealer Gamma Exposure (GEX)")
        st.caption("Positive GEX → dealers buy dips, dampen moves. "
                   "Negative GEX → dealers sell rallies, amplify moves. "
                   "Gamma flip level = inflection point.")

        with st.spinner("Computing GEX…"):
            gex_df = oa.gamma_exposure(calls, puts, spot_val, chosen_expiry)
        fig2 = _gex_chart(gex_df, spot_val)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True, key="gex_chart")
        else:
            st.info("Not enough data to compute GEX.")


    # ══════════════════════════ TAB: FLOW ═══════════════════════════════════
    with t_flow:
        st.markdown("#### ⚡ Options Flow Dashboard")
        with st.spinner("Analysing options flow…"):
            flow = oa.flow_analysis(calls, puts, spot_val)

        # ── Bull vs Bear flow bar ────────────────────────────────────────
        bias = flow.get("flow_bias", "—")
        bias_icon = "🟢 BULLISH" if bias == "BULLISH" else "🔴 BEARISH"
        st.markdown(f"**Overall Flow Bias: {bias_icon}**")
        fig_bar = _flow_bar(flow.get("bull_pct", 50), flow.get("bear_pct", 50))
        st.plotly_chart(fig_bar, use_container_width=True, key="flow_bar")

        # ── Flow metrics ──────────────────────────────────────────────────
        f1, f2, f3, f4 = st.columns(4)
        bull_m = flow.get("bull_flow_$", 0)
        bear_m = flow.get("bear_flow_$", 0)
        f1.metric("🟢 Call Premium $",  f"${bull_m:,.0f}")
        f2.metric("🔴 Put Premium $",   f"${bear_m:,.0f}")
        f3.metric("Put/Call Vol Ratio", flow.get("pcv_ratio", "—"))
        f4.metric("Put/Call OI Ratio",  flow.get("pco_ratio", "—"))

        st.markdown("---")
        st.markdown("#### ⚡ Top Unusual Activity (Vol/OI > 1.5×)")
        top = flow.get("top_unusual", pd.DataFrame())
        if not top.empty:
            top_display = top.copy()
            if "impliedVolatility" in top_display.columns:
                top_display["impliedVolatility"] = top_display["impliedVolatility"].apply(_fmt_iv)
            if "vol_oi_ratio" in top_display.columns:
                top_display["vol_oi_ratio"] = top_display["vol_oi_ratio"].apply(lambda x: f"{x:.1f}×")
            if "premium_$" in top_display.columns:
                top_display["premium_$"] = top_display["premium_$"].apply(lambda x: f"${x:,.0f}")
            rename_flow = {
                "vol_oi_ratio": "Vol/OI",
                "impliedVolatility": "IV",
                "openInterest": "OI",
                "premium_$": "$ Notional",
                "side": "Type",
                "itm": "ITM",
                "strike": "Strike",
                "volume": "Volume",
            }
            top_display = top_display.rename(columns=rename_flow)
            st.dataframe(top_display, use_container_width=True, hide_index=True)
            st.caption("⚡ High Vol/OI ratio suggests new positioning (not just rolling OI). "
                       "Large $ notional on single strike = possible institutional sweep.")
        else:
            st.info("No unusual activity detected (Vol/OI > 1.5×).")

        # ── Volume distribution pie ──────────────────────────────────────
        if flow.get("call_vol", 0) + flow.get("put_vol", 0) > 0:
            fig_pie = go.Figure(go.Pie(
                labels=["Calls", "Puts"],
                values=[flow["call_vol"], flow["put_vol"]],
                marker=dict(colors=[GREEN, RED]),
                hole=0.5,
                textfont=dict(color=WHITE),
            ))
            fig_pie.update_layout(
                paper_bgcolor=BG, font=dict(color=WHITE),
                height=260, margin=dict(l=10, r=10, t=30, b=10),
                title=dict(text="Volume Distribution", font=dict(size=13)),
                legend=dict(font=dict(color=WHITE)),
                showlegend=True,
            )
            st.plotly_chart(fig_pie, use_container_width=True, key="vol_pie")


# ─── Shared helpers used across tabs ─────────────────────────────────────────

def _flag_unusual(df: pd.DataFrame) -> pd.DataFrame:
    if "volume" in df.columns and "openInterest" in df.columns:
        df = df.copy()
        df["⚡"] = df.apply(
            lambda r: "⚡" if (r.get("openInterest") or 0) > 0
                             and (r.get("volume") or 0) > 0.5 * r["openInterest"]
                      else "",
            axis=1,
        )
    return df


def _max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    if calls.empty or puts.empty:
        return None
    try:
        strikes = sorted(set(calls["strike"].dropna()) & set(puts["strike"].dropna()))
        losses  = {}
        for s in strikes:
            c_loss = ((calls[calls["strike"] > s]["strike"] - s)
                      .clip(lower=0)
                      .multiply(calls[calls["strike"] > s]["openInterest"].fillna(0))
                      .sum())
            p_loss = ((s - puts[puts["strike"] < s]["strike"])
                      .clip(lower=0)
                      .multiply(puts[puts["strike"] < s]["openInterest"].fillna(0))
                      .sum())
            losses[s] = c_loss + p_loss
        return min(losses, key=losses.get) if losses else None
    except Exception:
        return None


def _oi_chart(calls: pd.DataFrame, puts: pd.DataFrame,
              mp: float | None, spot: float):
    if calls.empty and puts.empty:
        return
    try:
        fig = _dark_fig(height=280)
        if not calls.empty and "openInterest" in calls.columns:
            fig.add_trace(go.Bar(
                x=calls["strike"], y=calls["openInterest"].fillna(0),
                name="Calls OI", marker_color="rgba(0,200,83,0.7)",
            ))
        if not puts.empty and "openInterest" in puts.columns:
            fig.add_trace(go.Bar(
                x=puts["strike"], y=puts["openInterest"].fillna(0),
                name="Puts OI", marker_color="rgba(255,23,68,0.7)",
            ))
        if mp:
            fig.add_vline(x=mp, line_dash="dash", line_color=YELLOW,
                          annotation_text="Max Pain", annotation_font_color=YELLOW)
        if spot:
            fig.add_vline(x=spot, line_dash="dot", line_color=BLUE,
                          annotation_text="Spot", annotation_font_color=BLUE)
        fig.update_layout(barmode="group",
                          title=dict(text="Open Interest by Strike", font=dict(size=13)))
        st.plotly_chart(fig, use_container_width=True, key="oi_chart_v2")
    except Exception:
        pass
