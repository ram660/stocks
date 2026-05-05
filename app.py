"""
app.py
======
Main Streamlit entrypoint for the Stock Analysis Dashboard.
Run with:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

import config
import data_sources
import signals as sig_engine
import charts
import options_view

# ─────────────────────────────── Page config ────────────────────────────────
st.set_page_config(
    page_title="Stock Signal Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────────── Styles ───────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0e1117;
    color: #e6edf3;
}

/* Verdict badge */
.verdict-badge {
    display: inline-block;
    padding: 12px 28px;
    border-radius: 12px;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: 2px;
    margin-bottom: 8px;
}
.verdict-BUY  { background: rgba(0,200,83,0.18); color: #00c853; border: 2px solid #00c853; }
.verdict-SELL { background: rgba(255,23,68,0.18); color: #ff1744;  border: 2px solid #ff1744; }
.verdict-HOLD { background: rgba(100,100,100,0.18); color: #8b949e; border: 2px solid #8b949e; }
.verdict-WATCH{ background: rgba(255,214,0,0.18);   color: #ffd600; border: 2px solid #ffd600; }

/* Signal pill */
.pill-BUY   { background: rgba(0,200,83,0.15);  color: #00c853; padding: 3px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
.pill-SELL  { background: rgba(255,23,68,0.15);  color: #ff1744; padding: 3px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }
.pill-WATCH { background: rgba(255,214,0,0.15);  color: #ffd600; padding: 3px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }

/* Metric delta overrides */
[data-testid="stMetricValue"]       { font-size: 1.3rem; font-weight: 600; }
[data-testid="stMetricDelta"]       { font-size: 0.85rem; }

/* Sidebar */
[data-testid="stSidebar"] {
}
section[data-testid="stSidebar"] > div { padding-top: 1rem; }

div[data-testid="stTabs"] button { font-weight: 500; }

/* Scrollable signal list */
.signal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.signal-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 12px 16px;
    transition: transform 0.15s;
}
.signal-card:hover { transform: translateY(-2px); border-color: #30363d; }
.signal-card .name { font-weight: 600; font-size: 0.9rem; margin-bottom: 4px; }
.signal-card .note { color: #8b949e; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────── Sidebar ────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 Stock Dashboard")
    st.markdown("---")

    ticker = st.text_input("🔍 Ticker Symbol", value="AAPL",
                            help="Enter any US stock ticker, e.g. AAPL, TSLA, SPY").upper().strip()

    timeframe_label = st.selectbox("⏱ Timeframe",
                                    list(config.TIMEFRAME_OPTIONS.keys()),
                                    index=3)  # default 3 Months
    tf = config.TIMEFRAME_OPTIONS[timeframe_label]

    st.markdown("---")
    st.markdown("**📊 Chart Overlays**")
    show_ema9   = st.checkbox("EMA 9",   value=True)
    show_ema20  = st.checkbox("EMA 20",  value=True)
    show_ema50  = st.checkbox("EMA 50",  value=True)
    show_ema200 = st.checkbox("EMA 200", value=True)
    show_bb     = st.checkbox("Bollinger Bands", value=True)
    show_vwap   = st.checkbox("VWAP", value=True)
    show_macd   = st.checkbox("MACD Panel", value=True)
    selected_emas = [p for p, on in [(9, show_ema9), (20, show_ema20),
                                      (50, show_ema50), (200, show_ema200)] if on]

    st.markdown("---")
    auto_refresh = st.checkbox("🔄 Auto-refresh (60s)", value=False)


# ─────────────────────────────── Data load ───────────────────────────────────
if not ticker:
    st.warning("Please enter a ticker symbol in the sidebar.")
    st.stop()

with st.spinner(f"Loading data for **{ticker}**…"):
    df_raw    = data_sources.get_history(ticker, period=tf["period"], interval=tf["interval"])
    quote     = data_sources.get_quote(ticker)
    fund      = data_sources.get_fundamentals(ticker)

if df_raw.empty:
    st.error(f"Could not load data for **{ticker}**. Check the ticker symbol and try again.")
    st.stop()

# ────────────────────────────── Signal engine ────────────────────────────────
result   = sig_engine.run_signals(df_raw)
df       = result["df"]
verdict  = result["verdict"]
score    = result["score"]
signals  = result["signals"]


# ═══════════════════════════════ HEADER ROW ══════════════════════════════════
st.markdown(f"## {fund.get('name', ticker)}  `{ticker}`")
col_price, col_chg, col_vol, col_cap, col_sector = st.columns([2, 1.5, 1.5, 1.5, 2])

price  = quote.get("price")
change = quote.get("change", 0)
with col_price:
    st.metric("💲 Price", f"${price:,.2f}" if price else "—",
              delta=f"{change:+.2f}%")
with col_chg:
    color = "normal" if change >= 0 else "inverse"
    st.metric("1-Day Chg", f"{change:+.2f}%", delta=f"{change:+.2f}%", delta_color=color)
with col_vol:
    v = quote.get("volume")
    st.metric("📦 Avg Volume", f"{v/1_000_000:.1f}M" if v else "—")
with col_cap:
    mc = quote.get("mkt_cap")
    if mc:
        st.metric("Cap", f"${mc/1e9:.1f}B")
    else:
        st.metric("Cap", "—")
with col_sector:
    st.metric("Sector", fund.get("sector", "—"))

st.markdown("---")

# ═════════════════════════════ TABS ══════════════════════════════════════════
tab_chart, tab_signals, tab_opts, tab_settings = st.tabs(
    ["📉 Chart", "🎯 Signals", "📋 Options Chain", "⚙️ Settings"])


# ─────────────────────────────── TAB: CHART ──────────────────────────────────
with tab_chart:
    # Verdict badge + score
    vcol, scol = st.columns([2, 1])
    with vcol:
        st.markdown(
            f'<div class="verdict-badge verdict-{verdict}">'
            f'{"🟢" if verdict=="BUY" else "🔴" if verdict=="SELL" else "🟡" if verdict=="WATCH" else "⚪"} '
            f'{verdict}</div>',
            unsafe_allow_html=True)
        st.caption(f"Signal score: **{score:+d}** (≥+3 BUY · ≤-3 SELL)")
    with scol:
        buy_count  = sum(1 for s in signals if s["signal"] == "BUY")
        sell_count = sum(1 for s in signals if s["signal"] == "SELL")
        wtch_count = sum(1 for s in signals if s["signal"] == "WATCH")
        st.metric("🟢 BUY signals",  buy_count)
        st.metric("🔴 SELL signals", sell_count)
        st.metric("🟡 WATCH flags",  wtch_count)

    # Main chart
    fig = charts.build_main_chart(
        df, signals,
        show_emas=selected_emas,
        show_bb=show_bb,
        show_vwap=show_vwap,
    )
    st.plotly_chart(fig, use_container_width=True)

    # MACD sub-panel
    if show_macd:
        macd_fig = charts.build_macd_chart(df)
        if macd_fig:
            st.markdown("##### MACD")
            st.plotly_chart(macd_fig, use_container_width=True)

    # Fundamentals row
    if fund:
        st.markdown("---")
        fc = st.columns(5)
        pairs = [
            ("P/E (TTM)",      fund.get("pe"),         lambda x: f"{x:.1f}"),
            ("Fwd P/E",        fund.get("forward_pe"),  lambda x: f"{x:.1f}"),
            ("Beta",           fund.get("beta"),         lambda x: f"{x:.2f}"),
            ("52w High",       fund.get("52w_high"),     lambda x: f"${x:.2f}"),
            ("52w Low",        fund.get("52w_low"),      lambda x: f"${x:.2f}"),
        ]
        for col, (label, val, fmt) in zip(fc, pairs):
            with col:
                st.metric(label, fmt(val) if val else "—")


# ─────────────────────────────── TAB: SIGNALS ────────────────────────────────
with tab_signals:
    if not signals:
        st.info("No conditions triggered for the current timeframe and settings.")
    else:
        buy_sigs  = [s for s in signals if s["signal"] == "BUY"]
        sell_sigs = [s for s in signals if s["signal"] == "SELL"]
        watch_sig = [s for s in signals if s["signal"] == "WATCH"]

        def _render_signals(sig_list: list):
            html = '<div class="signal-grid">'
            for s in sig_list:
                pill = f'<span class="pill-{s["signal"]}">{s["signal"]}</span>'
                val  = f" · {s['value']}" if s.get("value") is not None else ""
                note = s.get("note", "")
                html += f"""
                <div class="signal-card">
                    <div class="name">{pill} {s['name']}{val}</div>
                    <div class="note">{note}</div>
                </div>"""
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)

        if buy_sigs:
            st.markdown("### 🟢 BUY Signals")
            _render_signals(buy_sigs)
        if sell_sigs:
            st.markdown("### 🔴 SELL Signals")
            _render_signals(sell_sigs)
        if watch_sig:
            st.markdown("### 🟡 WATCH Flags")
            _render_signals(watch_sig)

    # Indicator snapshot table
    st.markdown("---")
    st.markdown("#### 📊 Indicator Snapshot (last bar)")
    snap_cols = {
        "RSI":       "RSI",
        "MACD":      "MACD",
        "EMA 9":     "EMA_9",
        "EMA 20":    "EMA_20",
        "EMA 50":    "EMA_50",
        "EMA 200":   "EMA_200",
        "BB Upper":  "BB_Upper",
        "BB Lower":  "BB_Lower",
        "VWAP":      "VWAP",
    }
    snap_data = {}
    for label, col in snap_cols.items():
        if col in df.columns:
            last_val = df[col].dropna().iloc[-1] if not df[col].dropna().empty else None
            snap_data[label] = round(last_val, 2) if last_val is not None else "—"
    if snap_data:
        snap_df = pd.DataFrame(snap_data.items(), columns=["Indicator", "Last Value"])
        st.dataframe(snap_df, use_container_width=True, hide_index=True)


# ─────────────────────────────── TAB: OPTIONS ────────────────────────────────
with tab_opts:
    st.markdown(f"### Options Chain — **{ticker}**")
    options_view.render_options(ticker, spot=price or 0.0)


# ─────────────────────────────── TAB: SETTINGS ───────────────────────────────
with tab_settings:
    st.markdown("### ⚙️ Signal Conditions — Toggle & Tune")
    st.caption("Changes apply immediately to the signal engine above. "
               "To make permanent changes, edit `config.py`.")

    active_map = {}
    for cond_name, cfg in config.CONDITIONS.items():
        c1, c2 = st.columns([3, 1])
        with c1:
            enabled = st.checkbox(
                f"**{cond_name}** — {cfg.get('description', '')}",
                value=cfg.get("enabled", True),
                key=f"cond_{cond_name}",
            )
            active_map[cond_name] = enabled
        with c2:
            pill_color = {"BUY": "🟢", "SELL": "🔴", "WATCH": "🟡"}.get(cfg["signal"], "⚪")
            st.markdown(f"{pill_color} `{cfg['signal']}`  weight **{cfg.get('weight',1)}**")

    # Re-run signals with the new active map
    st.markdown("---")
    if st.button("🔁 Re-calculate Signals with current settings"):
        result2  = sig_engine.run_signals(df_raw, active_conditions=active_map)
        verdict2 = result2["verdict"]
        score2   = result2["score"]
        sigs2    = result2["signals"]
        st.markdown(
            f'<div class="verdict-badge verdict-{verdict2}">'
            f'{"🟢" if verdict2=="BUY" else "🔴" if verdict2=="SELL" else "🟡" if verdict2=="WATCH" else "⚪"} '
            f'{verdict2}  (score: {score2:+d})</div>',
            unsafe_allow_html=True)
        if sigs2:
            st.markdown(f"**{len(sigs2)} conditions triggered:**")
            for s in sigs2:
                pill = {"BUY":"🟢","SELL":"🔴","WATCH":"🟡"}.get(s["signal"],"⚪")
                st.markdown(f"- {pill} **{s['name']}** · {s.get('note','')}")
        else:
            st.info("No conditions triggered.")

    # Data-source info
    st.markdown("---")
    st.markdown("### 📡 Data Source Info")
    st.markdown(f"""
| Setting | Value |
|---|---|
| Primary source | `{config.DATA_SOURCE}` |
| Finnhub key set | `{'Yes' if config.FINNHUB_API_KEY else 'No'}` |
| Data (yfinance) | Free · Yahoo Finance · 15-min delayed |
| Options data | Via `yfinance` (Yahoo Finance) |

To enable real-time Finnhub quotes:
1. Get a free key at [finnhub.io](https://finnhub.io)
2. Open `config.py` and set `FINNHUB_API_KEY = "your_key_here"`
3. Set `DATA_SOURCE = "finnhub"`
""")


# ─────────────────────────────── Auto-refresh ────────────────────────────────
if auto_refresh:
    import time
    time.sleep(60)
    st.rerun()
