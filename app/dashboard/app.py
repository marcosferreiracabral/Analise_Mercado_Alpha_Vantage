"""Streamlit analytics dashboard for market intelligence."""

import sys
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
import streamlit as st

from app.config import settings
from app.dashboard.charts import (
    create_comparison_chart,
    create_correlation_heatmap,
    create_macd_chart,
    create_price_and_volume_chart,
    create_risk_chart,
    create_rsi_chart,
)
from app.dashboard.queries import (
    fetch_latest_quotes_summary,
    fetch_multi_symbol_history,
    fetch_symbol_history,
    get_available_symbols,
    get_pipeline_metadata,
)

st.set_page_config(
    page_title="Alpha Vantage Market Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        .metric-card {
            background: linear-gradient(135deg, rgba(22, 27, 34, 0.9) 0%, rgba(13, 17, 23, 0.9) 100%);
            border: 1px solid rgba(48, 54, 61, 0.6);
            border-radius: 12px;
            padding: 16px 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(8px);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            border-color: rgba(88, 166, 255, 0.4);
        }
        .metric-title {
            color: #8b949e;
            font-size: 0.85rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }
        .metric-value {
            color: #f0f6fc;
            font-size: 1.8rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .metric-delta-pos {
            color: #3fb950;
            font-size: 0.95rem;
            font-weight: 600;
            margin-top: 4px;
        }
        .metric-delta-neg {
            color: #f85149;
            font-size: 0.95rem;
            font-weight: 600;
            margin-top: 4px;
        }

        .badge-cloud {
            display: inline-block;
            background: rgba(56, 139, 253, 0.15);
            color: #58a6ff;
            border: 1px solid rgba(56, 139, 253, 0.4);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .badge-local {
            display: inline-block;
            background: rgba(163, 113, 247, 0.15);
            color: #d2a8ff;
            border: 1px solid rgba(163, 113, 247, 0.4);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_metric_card(
    title: str,
    value: str,
    delta: Optional[str] = None,
    is_positive: bool = True,
) -> None:
    """Renders custom styled metric card.

    Args:
        title: Header label for metric.
        value: Primary numerical or text string.
        delta: Optional relative delta indicator.
        is_positive: True for positive trend, False for negative.
    """
    delta_html = ""
    if delta:
        delta_class = "metric-delta-pos" if is_positive else "metric-delta-neg"
        arrow = "+" if is_positive else "-"
        delta_html = f'<div class="{delta_class}">{arrow} {delta}</div>'

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


st.sidebar.markdown("### Control Panel")
nav_page = st.sidebar.radio(
    "Navigation",
    [
        "Market Overview",
        "Historical Analysis",
        "Technical Indicators",
        "Asset Comparison",
    ],
    index=0,
)

available_symbols = get_available_symbols()
if not available_symbols:
    available_symbols = settings.all_default_symbols

selected_symbol = st.sidebar.selectbox("Primary Asset", available_symbols, index=0)

period_map = {
    "7 Days": 7,
    "1 Month": 30,
    "3 Months": 90,
    "6 Months": 180,
    "1 Year": 365,
    "Full History": None,
}
selected_period_label = st.sidebar.select_slider(
    "Analysis Period",
    options=list(period_map.keys()),
    value="6 Months",
)
selected_days = period_map[selected_period_label]

st.sidebar.markdown("---")
if st.sidebar.button("Refresh Cache", use_container_width=True):
    st.cache_data.clear()
    st.sidebar.success("Cache invalidated.")
    st.rerun()

metadata = get_pipeline_metadata()
backend_badge = (
    '<span class="badge-cloud">BigQuery Cloud</span>'
    if metadata.get("backend") == "bigquery"
    else '<span class="badge-local">Local Storage (SQLite/Parquet)</span>'
)
st.sidebar.markdown(f"**Storage Backend:** {backend_badge}", unsafe_allow_html=True)
if metadata.get("last_ingestion"):
    last_ing_str = str(metadata.get("last_ingestion"))
    st.sidebar.caption(f"Last Ingestion: `{last_ing_str[:19]}`")

col_h1, col_h2 = st.columns([0.7, 0.3])
with col_h1:
    st.title("Alpha Vantage Market Intelligence")
    st.caption("Financial Data Pipeline: Ingestion, Medallion Architecture, and Real-time Analytics")
with col_h2:
    st.markdown(
        f"""
        <div style="text-align: right; padding-top: 20px;">
            {backend_badge}
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

if nav_page == "Market Overview":
    st.subheader(f"Consolidated View: {selected_symbol}")

    quotes_df = fetch_latest_quotes_summary()
    target_quote = quotes_df[quotes_df["symbol"] == selected_symbol] if not quotes_df.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    if not target_quote.empty:
        q = target_quote.iloc[0]
        price_val = float(q.get("price", 0.0))
        chg_pct = float(q.get("change_percent", 0.0))
        vol = int(q.get("volume", 0))

        with c1:
            render_metric_card("Current Price", f"{price_val:,.2f}", f"{chg_pct:+.2f}%", chg_pct >= 0)
        with c2:
            render_metric_card(
                "Absolute Change",
                f"{float(q.get('change', 0.0)):+,.2f}",
                f"{chg_pct:+.2f}%",
                chg_pct >= 0,
            )
        with c3:
            render_metric_card("Session Volume", f"{vol:,.0f}")
        with c4:
            render_metric_card("Trade Date", str(q.get("latest_trading_day", "N/A")))
    else:
        with c1:
            render_metric_card("Current Price", "--")
        with c2:
            render_metric_card("Change", "--")
        with c3:
            render_metric_card("Volume", "--")
        with c4:
            render_metric_card("Date", "--")

    st.markdown("#### Monitored Pipeline Assets")
    if not quotes_df.empty:
        display_df = quotes_df[
            [
                "symbol",
                "price",
                "change",
                "change_percent",
                "volume",
                "latest_trading_day",
            ]
        ].copy()
        display_df.columns = [
            "Symbol",
            "Price",
            "Change",
            "Change (%)",
            "Volume",
            "Latest Trading Day",
        ]

        styler = display_df.style.format(
            {
                "Price": "{:,.2f}",
                "Change": "{:+,.2f}",
                "Change (%)": "{:+,.2f}%",
                "Volume": "{:,.0f}",
            }
        )

        def _color_variation(val: float) -> str:
            if val > 0:
                return "color: #3fb950; font-weight: bold;"
            elif val < 0:
                return "color: #f85149; font-weight: bold;"
            return "color: #8b949e;"

        if hasattr(styler, "map"):
            styler = styler.map(_color_variation, subset=["Change (%)"])
        else:
            styler = getattr(styler, "applymap")(_color_variation, subset=["Change (%)"])

        st.dataframe(
            styler,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No quote records in Gold layer. Run collect pipeline to load data.")

    history_df = fetch_symbol_history(selected_symbol, days=30)
    if not history_df.empty:
        st.markdown(f"#### Recent Trend (30 Days) - {selected_symbol}")
        fig = create_price_and_volume_chart(history_df, chart_type="line", show_sma=True)
        st.plotly_chart(fig, use_container_width=True)

elif nav_page == "Historical Analysis":
    st.subheader(f"Historical Price and Moving Averages: {selected_symbol}")

    col_opt1, col_opt2 = st.columns([0.5, 0.5])
    with col_opt1:
        chart_type = st.radio("Chart Type", ["Candlestick", "Line"], horizontal=True)
    with col_opt2:
        show_sma = st.checkbox("Display Moving Averages (SMA 7, 21, 50)", value=True)

    history_df = fetch_symbol_history(selected_symbol, days=selected_days)
    if not history_df.empty:
        fig = create_price_and_volume_chart(history_df, chart_type=chart_type.lower(), show_sma=show_sma)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Period Summary")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_metric_card("Period High", f"{history_df['high'].max():,.2f}")
        with c2:
            render_metric_card("Period Low", f"{history_df['low'].min():,.2f}")
        with c3:
            tot_ret = (
                (history_df["close"].iloc[-1] - history_df["close"].iloc[0]) / history_df["close"].iloc[0]
            ) * 100.0
            render_metric_card("Cumulative Return", f"{tot_ret:+.2f}%", is_positive=tot_ret >= 0)
        with c4:
            render_metric_card("Average Daily Volume", f"{history_df['volume'].mean():,.0f}")
    else:
        st.warning(f"No historical data available for {selected_symbol} in the selected period.")

elif nav_page == "Technical Indicators":
    st.subheader(f"Technical Indicators and Risk Analysis: {selected_symbol}")
    history_df = fetch_symbol_history(selected_symbol, days=selected_days)

    if not history_df.empty:
        tab_rsi, tab_macd, tab_risk = st.tabs(["RSI (14)", "MACD (12, 26, 9)", "Risk & Drawdown"])

        with tab_rsi:
            latest_rsi = history_df["rsi_14"].iloc[-1] if "rsi_14" in history_df.columns else 50.0
            rsi_status = (
                "Overbought (>70)"
                if latest_rsi > 70
                else "Oversold (<30)"
                if latest_rsi < 30
                else "Neutral (30-70)"
            )
            st.info(f"RSI (14): `{latest_rsi:.2f}` — Regime: **{rsi_status}**")
            fig_rsi = create_rsi_chart(history_df)
            st.plotly_chart(fig_rsi, use_container_width=True)

        with tab_macd:
            fig_macd = create_macd_chart(history_df)
            st.plotly_chart(fig_macd, use_container_width=True)

        with tab_risk:
            fig_risk = create_risk_chart(history_df)
            st.plotly_chart(fig_risk, use_container_width=True)
    else:
        st.warning(f"No technical indicator data available for {selected_symbol}.")

elif nav_page == "Asset Comparison":
    st.subheader("Performance Comparison and Correlation Matrix")
    multi_selected = st.multiselect(
        "Select assets to compare",
        options=available_symbols,
        default=available_symbols[: min(4, len(available_symbols))],
    )

    if len(multi_selected) >= 1:
        multi_df = fetch_multi_symbol_history(multi_selected, days=selected_days)
        if not multi_df.empty:
            st.markdown("#### Normalized Period Return (%)")
            fig_comp = create_comparison_chart(multi_df)
            st.plotly_chart(fig_comp, use_container_width=True)

            if len(multi_selected) >= 2:
                st.markdown("#### Pearson Correlation Matrix")
                fig_corr = create_correlation_heatmap(multi_df)
                st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.warning("Insufficient data for the selected assets.")
    else:
        st.info("Select at least one asset to display comparison.")
