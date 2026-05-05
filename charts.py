"""
charts.py
=========
All Plotly chart building functions.
"""
from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


COLORS = {
    "bg":     "#0e1117",
    "panel":  "#161b22",
    "green":  "#00c853",
    "red":    "#ff1744",
    "yellow": "#ffd600",
    "blue":   "#448aff",
    "white":  "#e6edf3",
    "muted":  "#8b949e",
    "ema9":   "#ff9800",
    "ema20":  "#e040fb",
    "ema50":  "#00bcd4",
    "ema200": "#f44336",
    "bb":     "rgba(100,180,255,0.25)",
}

EMA_COLORS = {9: "#ff9800", 20: "#e040fb", 50: "#00bcd4", 200: "#f44336"}


def build_main_chart(
    df: pd.DataFrame,
    signals: list[dict],
    show_emas: list[int] | None = None,
    show_bb: bool = True,
    show_vwap: bool = True,
) -> go.Figure:
    """
    Multi-panel chart:
      Panel 1 (65%): Candlestick + EMA overlays + BB + VWAP + signal markers
      Panel 2 (20%): Volume bars
      Panel 3 (15%): RSI
    """
    if show_emas is None:
        show_emas = [9, 20, 50, 200]

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.20, 0.15],
        vertical_spacing=0.02,
        subplot_titles=("", "Volume", "RSI"),
    )

    # ── Bollinger Bands (shaded ribbon) ────────────────────────────────────
    if show_bb and "BB_Upper" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Upper"],
            line=dict(color="rgba(100,180,255,0.4)", width=1),
            name="BB Upper", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Lower"],
            line=dict(color="rgba(100,180,255,0.4)", width=1),
            fill="tonexty", fillcolor=COLORS["bb"],
            name="BB Lower", showlegend=False,
        ), row=1, col=1)

    # ── VWAP ───────────────────────────────────────────────────────────────
    if show_vwap and "VWAP" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["VWAP"],
            line=dict(color="#ffd600", width=1.2, dash="dot"),
            name="VWAP",
        ), row=1, col=1)

    # ── EMAs ───────────────────────────────────────────────────────────────
    for p in show_emas:
        col = f"EMA_{p}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col],
                line=dict(color=EMA_COLORS.get(p, "#aaa"), width=1),
                name=f"EMA {p}",
            ), row=1, col=1)

    # ── Candlestick ────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        increasing_line_color=COLORS["green"],
        decreasing_line_color=COLORS["red"],
        name="Price",
    ), row=1, col=1)

    # ── Signal markers ─────────────────────────────────────────────────────
    buy_dates  = [s for s in signals if s["signal"] == "BUY"]
    sell_dates = [s for s in signals if s["signal"] == "SELL"]

    if buy_dates:
        last_price = df["Low"].iloc[-1]
        fig.add_trace(go.Scatter(
            x=[df.index[-1]],
            y=[last_price * 0.98],
            mode="markers+text",
            marker=dict(symbol="triangle-up", size=16, color=COLORS["green"]),
            text=["▲ BUY"],
            textposition="bottom center",
            textfont=dict(color=COLORS["green"], size=11),
            name="BUY Signal",
            showlegend=False,
        ), row=1, col=1)

    if sell_dates:
        last_price = df["High"].iloc[-1]
        fig.add_trace(go.Scatter(
            x=[df.index[-1]],
            y=[last_price * 1.02],
            mode="markers+text",
            marker=dict(symbol="triangle-down", size=16, color=COLORS["red"]),
            text=["▼ SELL"],
            textposition="top center",
            textfont=dict(color=COLORS["red"], size=11),
            name="SELL Signal",
            showlegend=False,
        ), row=1, col=1)

    # ── Volume ─────────────────────────────────────────────────────────────
    vol_colors = [
        COLORS["green"] if df["Close"].iloc[i] >= df["Open"].iloc[i]
        else COLORS["red"]
        for i in range(len(df))
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors,
        name="Volume", showlegend=False,
    ), row=2, col=1)

    if "Vol_Avg" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Vol_Avg"],
            line=dict(color=COLORS["yellow"], width=1, dash="dash"),
            name="Vol MA", showlegend=False,
        ), row=2, col=1)

    # ── RSI ────────────────────────────────────────────────────────────────
    if "RSI" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["RSI"],
            line=dict(color=COLORS["blue"], width=1.5),
            name="RSI",
        ), row=3, col=1)
        for level, color in [(30, COLORS["green"]), (70, COLORS["red"]), (50, COLORS["muted"])]:
            fig.add_hline(y=level, line_dash="dash",
                          line_color=color, line_width=0.8, row=3, col=1)

    # ── Layout ─────────────────────────────────────────────────────────────
    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font=dict(color=COLORS["white"], family="Inter, sans-serif"),
        xaxis_rangeslider_visible=False,
        legend=dict(
            bgcolor="rgba(0,0,0,0.4)",
            bordercolor=COLORS["muted"],
            borderwidth=1,
            orientation="h",
            y=-0.05,
        ),
        margin=dict(l=10, r=10, t=30, b=10),
        height=680,
        hovermode="x unified",
    )
    for ax in ["xaxis", "xaxis2", "xaxis3"]:
        fig.update_layout(**{ax: dict(
            gridcolor="#21262d",
            showgrid=True,
            zeroline=False,
        )})
    for ax in ["yaxis", "yaxis2", "yaxis3"]:
        fig.update_layout(**{ax: dict(
            gridcolor="#21262d",
            showgrid=True,
            zeroline=False,
        )})

    return fig


def build_macd_chart(df: pd.DataFrame) -> go.Figure | None:
    if "MACD" not in df.columns:
        return None

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df.index, y=df["MACD_Hist"],
        marker_color=[COLORS["green"] if v >= 0 else COLORS["red"] for v in df["MACD_Hist"].fillna(0)],
        name="Histogram",
    ))
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"],
                             line=dict(color=COLORS["blue"], width=1.5), name="MACD"))
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"],
                             line=dict(color=COLORS["yellow"], width=1.5), name="Signal"))

    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font=dict(color=COLORS["white"]),
        height=200,
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", y=-0.3),
        xaxis=dict(gridcolor="#21262d"),
        yaxis=dict(gridcolor="#21262d"),
        hovermode="x unified",
    )
    return fig
