"""Interactive Plotly financial visualizations with dark theme formatting."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BG_COLOR = "#0e1117"
CARD_BG = "#161b22"
GRID_COLOR = "#21262d"
TEXT_COLOR = "#c9d1d9"
GREEN_COLOR = "#26a69a"
RED_COLOR = "#ef5350"
CYAN_COLOR = "#00e5ff"
ORANGE_COLOR = "#ff9100"
PURPLE_COLOR = "#d500f9"


def apply_custom_theme(fig: go.Figure, title: str | None = None) -> go.Figure:
    """Applies standardized dark theme formatting to a Plotly figure.

    Args:
        fig: Target Plotly figure.
        title: Optional chart title.

    Returns:
        Formatted Plotly figure.
    """
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Roboto, sans-serif", color=TEXT_COLOR, size=12),
        margin=dict(l=40, r=40, t=50 if title else 25, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(22, 27, 34, 0.8)",
            bordercolor=GRID_COLOR,
            borderwidth=1,
        ),
        hovermode="x unified",
    )
    if title:
        fig.update_layout(
            title=dict(
                text=f"<b>{title}</b>",
                font=dict(size=16, color="#f0f6fc"),
                x=0.01,
                y=0.98,
            )
        )
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor=GRID_COLOR,
        zeroline=False,
        showline=True,
        linecolor=GRID_COLOR,
    )
    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor=GRID_COLOR,
        zeroline=False,
        showline=True,
        linecolor=GRID_COLOR,
    )
    return fig


def create_price_and_volume_chart(
    df: pd.DataFrame,
    chart_type: str = "candlestick",
    show_sma: bool = True,
) -> go.Figure:
    """Constructs synchronized price (Candlestick/Line) and volume secondary chart.

    Args:
        df: DataFrame containing date, open, high, low, close, volume, and SMAs.
        chart_type: 'candlestick' or 'line'.
        show_sma: Flag to overlay moving averages.

    Returns:
        Dual-axis Plotly figure.
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
    )

    dates = df["date"]

    if chart_type.lower() == "candlestick":
        fig.add_trace(
            go.Candlestick(
                x=dates,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="OHLC",
                increasing_line_color=GREEN_COLOR,
                decreasing_line_color=RED_COLOR,
            ),
            row=1,
            col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=df["close"],
                mode="lines",
                name="Close",
                line=dict(color=CYAN_COLOR, width=2),
                fill="tozeroy",
                fillcolor="rgba(0, 229, 255, 0.08)",
            ),
            row=1,
            col=1,
        )

    if show_sma:
        if "sma_7" in df.columns and df["sma_7"].notnull().any():
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=df["sma_7"],
                    mode="lines",
                    name="SMA 7",
                    line=dict(color=CYAN_COLOR, width=1.5, dash="dot"),
                ),
                row=1,
                col=1,
            )
        if "sma_21" in df.columns and df["sma_21"].notnull().any():
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=df["sma_21"],
                    mode="lines",
                    name="SMA 21",
                    line=dict(color=ORANGE_COLOR, width=1.8),
                ),
                row=1,
                col=1,
            )
        if "sma_50" in df.columns and df["sma_50"].notnull().any():
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=df["sma_50"],
                    mode="lines",
                    name="SMA 50",
                    line=dict(color=PURPLE_COLOR, width=1.5, dash="dash"),
                ),
                row=1,
                col=1,
            )

    vol_colors = [GREEN_COLOR if c >= o else RED_COLOR for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(
            x=dates,
            y=df["volume"],
            name="Volume",
            marker_color=vol_colors,
            opacity=0.7,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(xaxis_rangeslider_visible=False)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

    return apply_custom_theme(fig, "Historical Price and Volume")


def create_rsi_chart(df: pd.DataFrame) -> go.Figure:
    """Builds RSI (14) indicator chart with threshold levels.

    Args:
        df: DataFrame containing date and rsi_14.

    Returns:
        Plotly figure.
    """
    fig = go.Figure()
    dates = df["date"]
    rsi = df["rsi_14"]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=rsi,
            mode="lines",
            name="RSI (14)",
            line=dict(color=PURPLE_COLOR, width=2),
        )
    )

    fig.add_hline(
        y=70,
        line_dash="dash",
        line_color=RED_COLOR,
        annotation_text="Overbought (70)",
        annotation_position="top right",
    )
    fig.add_hline(y=50, line_dash="dot", line_color="#8b949e", opacity=0.5)
    fig.add_hline(
        y=30,
        line_dash="dash",
        line_color=GREEN_COLOR,
        annotation_text="Oversold (30)",
        annotation_position="bottom right",
    )
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(110, 118, 129, 0.08)", line_width=0)
    fig.update_yaxes(range=[0, 100], title_text="RSI")

    return apply_custom_theme(fig, "Relative Strength Index (RSI 14)")


def create_macd_chart(df: pd.DataFrame) -> go.Figure:
    """Builds MACD oscillator with MACD line, signal line, and histogram.

    Args:
        df: DataFrame containing date, macd_line, macd_signal, macd_hist.

    Returns:
        Plotly figure.
    """
    fig = go.Figure()
    dates = df["date"]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=df["macd_line"],
            mode="lines",
            name="MACD Line (12, 26)",
            line=dict(color=CYAN_COLOR, width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=df["macd_signal"],
            mode="lines",
            name="Signal Line (9)",
            line=dict(color=ORANGE_COLOR, width=1.8),
        )
    )

    hist_colors = [GREEN_COLOR if h >= 0 else RED_COLOR for h in df["macd_hist"]]
    fig.add_trace(
        go.Bar(
            x=dates,
            y=df["macd_hist"],
            name="Histogram",
            marker_color=hist_colors,
            opacity=0.75,
        )
    )

    fig.add_hline(y=0, line_color=GRID_COLOR, line_width=1)
    fig.update_yaxes(title_text="MACD")
    return apply_custom_theme(fig, "Moving Average Convergence Divergence (MACD)")


def create_comparison_chart(df: pd.DataFrame) -> go.Figure:
    """Builds normalized percentage cumulative return comparison across assets.

    Args:
        df: DataFrame containing symbol, date, close.

    Returns:
        Plotly figure.
    """
    fig = go.Figure()

    for symbol, group in df.groupby("symbol"):
        g = group.sort_values(by="date").copy()
        first_close = g["close"].iloc[0]
        if first_close and first_close > 0:
            norm_return = ((g["close"] - first_close) / first_close) * 100.0
            fig.add_trace(
                go.Scatter(
                    x=g["date"],
                    y=norm_return,
                    mode="lines",
                    name=symbol,
                    line=dict(width=2),
                )
            )

    fig.add_hline(y=0, line_dash="dash", line_color="#8b949e", line_width=1)
    fig.update_yaxes(title_text="Cumulative Return (%)", ticksuffix="%")
    return apply_custom_theme(fig, "Normalized Relative Return (%)")


def create_correlation_heatmap(df: pd.DataFrame) -> go.Figure:
    """Builds Pearson correlation heatmap for closing prices.

    Args:
        df: DataFrame containing date, symbol, close.

    Returns:
        Plotly figure with correlation matrix heatmap.
    """
    pivoted = df.pivot_table(index="date", columns="symbol", values="close").dropna()
    if pivoted.empty or pivoted.shape[1] < 2:
        fig = go.Figure()
        fig.add_annotation(
            text="Insufficient data for correlation (select at least 2 assets with overlapping history).",
            showarrow=False,
        )
        return apply_custom_theme(fig, "Correlation Matrix")

    corr = pivoted.corr().round(2)
    symbols = corr.columns.tolist()

    fig = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=symbols,
            y=symbols,
            colorscale="Viridis",
            zmin=-1.0,
            zmax=1.0,
            text=corr.values,
            texttemplate="%{text}",
            textfont=dict(size=14, color="#ffffff"),
            colorbar=dict(title="Correlation (r)"),
        )
    )
    return apply_custom_theme(fig, "Pearson Correlation Matrix")


def create_risk_chart(df: pd.DataFrame) -> go.Figure:
    """Builds annualized volatility and maximum drawdown subplots.

    Args:
        df: DataFrame containing date, volatility_21d, max_drawdown_252d.

    Returns:
        Plotly figure with dual risk metrics subplots.
    """
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.5, 0.5])
    dates = df["date"]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=df["volatility_21d"],
            mode="lines",
            name="21d Annualized Volatility (%)",
            line=dict(color=ORANGE_COLOR, width=2),
            fill="tozeroy",
            fillcolor="rgba(255, 145, 0, 0.08)",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=-df["max_drawdown_252d"].abs(),
            mode="lines",
            name="252d Drawdown (%)",
            line=dict(color=RED_COLOR, width=2),
            fill="tozeroy",
            fillcolor="rgba(239, 83, 80, 0.15)",
        ),
        row=2,
        col=1,
    )

    fig.update_yaxes(title_text="Volatility (%)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)

    return apply_custom_theme(fig, "Risk Metrics: Volatility and Drawdown")
