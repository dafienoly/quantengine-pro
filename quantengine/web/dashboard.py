"""
QuantEngine Pro - Plotly Dash Dashboard
=========================================
Interactive web dashboard with 5 panels:
1. Overview - Equity curve, positions, P&L, risk gauges
2. Strategy - Signal flow, performance comparison
3. Backtest - Config → run → report visualization
4. AI Analysis - Sentiment timeline, word cloud, AI picks
5. Logs - System logs, trade records, alerts
"""

import json
from datetime import datetime
from typing import Dict, Optional

import dash
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import dcc, html
from dash.dependencies import Input, Output
from loguru import logger


def create_dashboard(
    backtest_engine=None,
    strategy_registry=None,
    market_overview=None,
) -> dash.Dash:
    """
    Create and configure the Plotly Dash dashboard.

    Args:
        backtest_engine: BacktestEngine instance for data
        strategy_registry: StrategyRegistry instance
        market_overview: MarketOverview instance

    Returns:
        Configured Dash application
    """
    app = dash.Dash(
        __name__,
        title="QuantEngine Pro Dashboard",
        update_title=None,
    )

    # ---- Layout ----
    app.layout = html.Div([
        # Header
        html.Div([
            html.H1("📊 QuantEngine Pro", style={"color": "#ffffff", "margin": "0"}),
            html.Span("v0.1.0", style={"color": "#888", "fontSize": "14px"}),
        ], style={
            "backgroundColor": "#1a1a2e",
            "padding": "15px 30px",
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
        }),

        # Tab navigation
        dcc.Tabs(id="tabs", value="overview", children=[
            dcc.Tab(label="📈 Overview", value="overview"),
            dcc.Tab(label="🎯 Strategies", value="strategies"),
            dcc.Tab(label="⚡ Backtest", value="backtest"),
            dcc.Tab(label="🤖 AI Analysis", value="ai"),
            dcc.Tab(label="📋 Logs", value="logs"),
        ], style={"backgroundColor": "#16213e"}),

        # Tab content
        html.Div(id="tab-content", style={"padding": "20px"}),

        # Hidden data store for refreshing
        dcc.Store(id="data-store"),

        # Auto-refresh interval (every 5 seconds)
        dcc.Interval(id="refresh-interval", interval=5000),
    ], style={
        "backgroundColor": "#0f0f23",
        "minHeight": "100vh",
        "fontFamily": "Arial, sans-serif",
        "color": "#e0e0e0",
    })

    # ---- Callbacks ----

    @app.callback(
        Output("tab-content", "children"),
        Input("tabs", "value"),
    )
    def render_tab(tab: str):
        """Render the selected tab content."""
        if tab == "overview":
            return _render_overview_tab()
        elif tab == "strategies":
            return _render_strategies_tab()
        elif tab == "backtest":
            return _render_backtest_tab()
        elif tab == "ai":
            return _render_ai_tab()
        elif tab == "logs":
            return _render_logs_tab()
        return html.Div("Unknown tab")

    return app


def _render_overview_tab() -> html.Div:
    """Render the Overview tab with equity, positions, P&L, risk gauges."""
    return html.Div([
        # Top row: Key metrics
        html.Div([
            _metric_card("💰 Total Equity", "¥0.00", "#00ff88"),
            _metric_card("📊 Daily P&L", "+¥0.00", "#00ff88"),
            _metric_card("📉 Max Drawdown", "0.00%", "#ff4444"),
            _metric_card("🎯 Sharpe Ratio", "0.00", "#4488ff"),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "15px", "marginBottom": "20px"}),

        # Middle row: Equity curve chart
        html.Div([
            html.H3("Equity Curve"),
            dcc.Graph(
                id="equity-chart",
                figure=_empty_chart("Equity Curve (No data yet)"),
                style={"height": "400px"},
            ),
        ], style=_card_style()),

        # Bottom row: Positions and trades
        html.Div([
            # Positions table
            html.Div([
                html.H3("Current Positions"),
                html.Div(id="positions-table", children="No positions"),
            ], style={**_card_style(), "flex": "1"}),

            # Recent trades
            html.Div([
                html.H3("Recent Trades"),
                html.Div(id="trades-table", children="No trades"),
            ], style={**_card_style(), "flex": "1"}),
        ], style={"display": "flex", "gap": "15px", "marginTop": "15px"}),
    ])


def _render_strategies_tab() -> html.Div:
    """Render Strategies tab with performance comparison."""
    return html.Div([
        html.H3("Strategy Performance"),
        dcc.Graph(
            id="strategy-comparison",
            figure=_empty_chart("Strategy Performance Comparison"),
        ),
        html.Div(id="strategy-details", style={"marginTop": "20px"}),
    ])


def _render_backtest_tab() -> html.Div:
    """Render Backtest tab with config and results."""
    return html.Div([
        html.H3("Backtest Configuration"),
        html.Div([
            html.Label("Strategy"),
            dcc.Dropdown(
                id="backtest-strategy",
                options=[
                    {"label": "Dual Thrust", "value": "dual_thrust"},
                    {"label": "Turtle", "value": "turtle"},
                    {"label": "Bollinger", "value": "bollinger"},
                    {"label": "Dual MA", "value": "dual_ma"},
                    {"label": "R Breaker", "value": "r_breaker"},
                    {"label": "Grid + MA", "value": "grid_ma"},
                ],
                value="dual_thrust",
                style={"color": "#000"},
            ),
            html.Label("Symbol"),
            dcc.Input(id="backtest-symbol", value="ETH/USDT", type="text"),
            html.Label("Timeframe"),
            dcc.Dropdown(
                id="backtest-timeframe",
                options=[
                    {"label": "5 min", "value": "5m"},
                    {"label": "15 min", "value": "15m"},
                    {"label": "1 hour", "value": "1h"},
                    {"label": "1 day", "value": "1d"},
                ],
                value="1h",
                style={"color": "#000"},
            ),
            html.Label("Initial Capital"),
            dcc.Input(id="backtest-capital", value=100000, type="number"),
            html.Button("▶ Run Backtest", id="run-backtest-btn", style={"marginTop": "15px", "padding": "10px 20px"}),
        ], style={**_card_style(), "maxWidth": "500px"}),

        html.Div(id="backtest-results", style={"marginTop": "20px"}),
    ])


def _render_ai_tab() -> html.Div:
    """Render AI Analysis tab with sentiment and picks."""
    return html.Div([
        html.H3("🤖 AI-Powered Analysis"),

        # News sentiment timeline
        html.Div([
            html.H4("News Sentiment Timeline"),
            dcc.Graph(
                id="sentiment-timeline",
                figure=_empty_chart("Sentiment Timeline (requires LLM service)"),
            ),
        ], style=_card_style()),

        # AI stock picks
        html.Div([
            html.H4("AI Stock/Crypto Picks"),
            html.Div(id="ai-picks", children="No AI picks available. Start LLM service to see recommendations."),
        ], style={**_card_style(), "marginTop": "15px"}),

        # Trading signal recommendations
        html.Div([
            html.H4("Trading Signal Recommendations"),
            html.Div(id="signal-recommendations", children="No active signals."),
        ], style={**_card_style(), "marginTop": "15px"}),
    ])


def _render_logs_tab() -> html.Div:
    """Render Logs tab with system events."""
    return html.Div([
        html.H3("System Logs"),
        html.Div(id="system-logs", style={
            "backgroundColor": "#111",
            "padding": "15px",
            "borderRadius": "5px",
            "fontFamily": "monospace",
            "fontSize": "12px",
            "maxHeight": "600px",
            "overflowY": "scroll",
        }, children="System logs will appear here..."),

        html.H3("Trade Records", style={"marginTop": "20px"}),
        html.Div(id="trade-records-log", children="Trade records will appear here..."),
    ])


# ---- Helper Components ----

def _metric_card(title: str, value: str, color: str) -> html.Div:
    """Create a metric display card."""
    return html.Div([
        html.Div(title, style={"fontSize": "12px", "color": "#888", "marginBottom": "5px"}),
        html.Div(value, style={"fontSize": "24px", "fontWeight": "bold", "color": color}),
    ], style={
        "backgroundColor": "#16213e",
        "padding": "15px",
        "borderRadius": "8px",
        "textAlign": "center",
    })


def _card_style() -> Dict:
    """Standard card style."""
    return {
        "backgroundColor": "#16213e",
        "padding": "20px",
        "borderRadius": "8px",
        "marginBottom": "10px",
    }


def _empty_chart(title: str) -> go.Figure:
    """Create an empty chart with placeholder message."""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_dark",
        paper_bgcolor="#16213e",
        plot_bgcolor="#16213e",
        font_color="#e0e0e0",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{
            "text": title,
            "showarrow": False,
            "font": {"size": 16, "color": "#666"},
        }],
    )
    return fig
