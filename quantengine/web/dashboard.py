"""
QuantEngine Pro - Plotly Dash Dashboard
=========================================
Interactive web dashboard with 5 panels:
1. Overview - Equity curve, positions, P&L, risk gauges
2. Strategy - Signal flow, performance comparison
3. Backtest - Config → run → report visualization
4. AI Analysis - Sentiment timeline, AI picks
5. Logs - System logs, trade records, alerts
"""

from typing import Dict

import dash
import plotly.graph_objects as go
from dash import dcc, html
from dash.dependencies import Input, Output


def create_dashboard(backtest_engine=None, strategy_registry=None, market_overview=None) -> dash.Dash:
    """Create the Plotly Dash dashboard application."""
    app = dash.Dash(__name__, title="QuantEngine Pro Dashboard", update_title=None)

    app.layout = html.Div([
        # Header
        html.Div([
            html.H1("QuantEngine Pro", style={"color": "#fff", "margin": "0", "fontSize": "20px"}),
            html.Span("v0.1.0", style={"color": "#888", "fontSize": "12px"}),
        ], style={"backgroundColor": "#1a1a2e", "padding": "12px 30px",
                   "display": "flex", "justifyContent": "space-between", "alignItems": "center"}),

        # Tabs
        dcc.Tabs(id="tabs", value="overview", children=[
            dcc.Tab(label="Overview", value="overview"),
            dcc.Tab(label="Strategies", value="strategies"),
            dcc.Tab(label="Backtest", value="backtest"),
            dcc.Tab(label="AI Analysis", value="ai"),
            dcc.Tab(label="Logs", value="logs"),
        ], style={"backgroundColor": "#16213e"}),

        # Tab content
        html.Div(id="tab-content", style={"padding": "20px"}),

        # Auto-refresh
        dcc.Interval(id="refresh", interval=5000),
    ], style={"backgroundColor": "#0f0f23", "minHeight": "100vh",
              "fontFamily": "Arial,sans-serif", "color": "#e0e0e0"})

    @app.callback(Output("tab-content", "children"), Input("tabs", "value"))
    def render_tab(tab: str):
        if tab == "overview":
            return _overview_tab()
        elif tab == "strategies":
            return _strategies_tab()
        elif tab == "backtest":
            return _backtest_tab()
        elif tab == "ai":
            return _ai_tab()
        elif tab == "logs":
            return _logs_tab()
        return html.Div("Unknown tab")

    return app


def _card(title: str, value: str, color: str = "#00ff88") -> html.Div:
    return html.Div([
        html.Div(title, style={"fontSize": "12px", "color": "#888"}),
        html.Div(value, style={"fontSize": "22px", "fontWeight": "bold", "color": color}),
    ], style={"backgroundColor": "#16213e", "padding": "15px", "borderRadius": "8px", "textAlign": "center"})


def _panel(children, title: str = None) -> html.Div:
    return html.Div([
        html.H3(title) if title else None,
        *([children] if not isinstance(children, list) else children),
    ], style={"backgroundColor": "#16213e", "padding": "20px", "borderRadius": "8px", "marginBottom": "10px"})


def _empty_chart(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title, template="plotly_dark",
        paper_bgcolor="#16213e", plot_bgcolor="#16213e",
        font_color="#e0e0e0",
        annotations=[{"text": title, "showarrow": False, "font": {"size": 14, "color": "#666"}}],
    )
    return fig


def _overview_tab() -> html.Div:
    return html.Div([
        html.Div([_card("Total Equity", "\xA50.00"), _card("Daily P&L", "+\xA50.00"),
                   _card("Max Drawdown", "0.00%", "#ff4444"), _card("Sharpe", "0.00", "#4488ff")],
                 style={"display": "grid", "gridTemplateColumns": "repeat(4,1fr)", "gap": "15px", "marginBottom": "15px"}),
        _panel(dcc.Graph(id="equity-chart", figure=_empty_chart("Equity Curve"), style={"height": "350px"}), "Equity Curve"),
        html.Div([
            _panel(html.Div("No positions", id="positions-table"), "Positions"),
            _panel(html.Div("No trades", id="trades-table"), "Recent Trades"),
        ], style={"display": "flex", "gap": "15px", "marginTop": "15px"}),
    ])


def _strategies_tab() -> html.Div:
    return html.Div([
        _panel(dcc.Graph(id="strategy-chart", figure=_empty_chart("Strategy Performance Comparison")), "Strategy Performance"),
        html.Div(id="strategy-details", style={"marginTop": "15px"}),
    ])


def _backtest_tab() -> html.Div:
    return html.Div([
        _panel([
            html.Label("Strategy"), dcc.Dropdown(
                id="bt-strategy", options=[
                    {"label": s, "value": s} for s in
                    ["dual_thrust","turtle","bollinger","dual_ma","r_breaker","grid_ma"]
                ], value="dual_thrust", style={"color": "#000"}),
            html.Label("Symbol"), dcc.Input(id="bt-symbol", value="ETH/USDT", type="text"),
            html.Label("Timeframe"), dcc.Dropdown(
                id="bt-timeframe", options=[
                    {"label": f, "value": f} for f in ["5m","15m","1h","1d"]
                ], value="1h", style={"color": "#000"}),
            html.Label("Initial Capital"), dcc.Input(id="bt-capital", value=100000, type="number"),
            html.Button("Run Backtest", id="run-bt-btn", style={"marginTop": "15px", "padding": "8px 20px"}),
        ], "Backtest Configuration"),
        html.Div(id="backtest-results", style={"marginTop": "15px"}),
    ])


def _ai_tab() -> html.Div:
    return html.Div([
        _panel(dcc.Graph(id="sentiment-chart", figure=_empty_chart("News Sentiment Timeline")), "AI News Sentiment"),
        _panel(html.Div("No AI picks available. Start LLM service."), "AI Picks"),
        _panel(html.Div("No active signals."), "Signal Recommendations"),
    ])


def _logs_tab() -> html.Div:
    return html.Div([
        _panel(html.Div("System logs...", style={
            "backgroundColor": "#111", "padding": "10px", "borderRadius": "5px",
            "fontFamily": "monospace", "fontSize": "12px", "maxHeight": "400px", "overflowY": "scroll",
        }), "System Logs"),
        _panel(html.Div("Trade records..."), "Trade History"),
    ])
