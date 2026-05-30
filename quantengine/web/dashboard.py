"""
QuantEngine Pro - Plotly Dash 仪表盘
=========================================
5 个面板的交互式 Web 看板：
1. 总览 - 权益曲线、持仓、盈亏、风险指标
2. 策略 - 信号流、表现对比
3. 回测 - 配置 → 运行 → 报告可视化
4. AI分析 - 情感时间线、AI推荐
5. 日志 - 系统日志、交易记录、告警
"""

from typing import Dict

import dash
import plotly.graph_objects as go
from dash import dcc, html
from dash.dependencies import Input, Output


def create_dashboard(backtest_engine=None, strategy_registry=None, market_overview=None) -> dash.Dash:
    """Create the Plotly Dash dashboard application."""
    app = dash.Dash(__name__, title="量化引擎专业版", update_title=None)

    app.layout = html.Div([
        # Header
        html.Div([
            html.H1("量化引擎专业版", style={"color": "#fff", "margin": "0", "fontSize": "20px"}),
            html.Span("v0.1.0", style={"color": "#888", "fontSize": "12px"}),
        ], style={"backgroundColor": "#1a1a2e", "padding": "12px 30px",
                   "display": "flex", "justifyContent": "space-between", "alignItems": "center"}),

        # Tabs
        dcc.Tabs(id="tabs", value="overview", children=[
            dcc.Tab(label="总览", value="overview"),
            dcc.Tab(label="策略", value="strategies"),
            dcc.Tab(label="回测", value="backtest"),
            dcc.Tab(label="AI分析", value="ai"),
            dcc.Tab(label="日志", value="logs"),
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
        return html.Div("未知标签页")

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
        html.Div([_card("总权益", "\xA50.00"), _card("当日盈亏", "+\xA50.00"),
                   _card("最大回撤", "0.00%", "#ff4444"), _card("夏普比率", "0.00", "#4488ff")],
                 style={"display": "grid", "gridTemplateColumns": "repeat(4,1fr)", "gap": "15px", "marginBottom": "15px"}),
        _panel(dcc.Graph(id="equity-chart", figure=_empty_chart("权益曲线"), style={"height": "350px"}), "权益曲线"),
        html.Div([
            _panel(html.Div("暂无持仓", id="positions-table"), "持仓"),
            _panel(html.Div("暂无交易", id="trades-table"), "最近交易"),
        ], style={"display": "flex", "gap": "15px", "marginTop": "15px"}),
    ])


def _strategies_tab() -> html.Div:
    return html.Div([
        _panel(dcc.Graph(id="strategy-chart", figure=_empty_chart("策略表现对比")), "策略表现"),
        html.Div(id="strategy-details", style={"marginTop": "15px"}),
    ])


def _backtest_tab() -> html.Div:
    return html.Div([
        _panel([
            html.Label("策略"), dcc.Dropdown(
                id="bt-strategy", options=[
                    {"label": s, "value": s} for s in
                    ["dual_thrust","turtle","bollinger","dual_ma","r_breaker","grid_ma"]
                ], value="dual_thrust", style={"color": "#000"}),
            html.Label("交易对"), dcc.Input(id="bt-symbol", value="ETH/USDT", type="text"),
            html.Label("周期"), dcc.Dropdown(
                id="bt-timeframe", options=[
                    {"label": f, "value": f} for f in ["5m","15m","1h","1d"]
                ], value="1h", style={"color": "#000"}),
            html.Label("初始资金"), dcc.Input(id="bt-capital", value=100000, type="number"),
            html.Button("运行回测", id="run-bt-btn", style={"marginTop": "15px", "padding": "8px 20px"}),
        ], "回测配置"),
        html.Div(id="backtest-results", style={"marginTop": "15px"}),
    ])


def _ai_tab() -> html.Div:
    return html.Div([
        _panel(dcc.Graph(id="sentiment-chart", figure=_empty_chart("新闻情感时间线")), "AI新闻情感"),
        _panel(html.Div("暂无AI推荐，请启动LLM服务。"), "AI推荐"),
        _panel(html.Div("暂无活跃信号。"), "信号推荐"),
    ])


def _logs_tab() -> html.Div:
    return html.Div([
        _panel(html.Div("系统日志...", style={
            "backgroundColor": "#111", "padding": "10px", "borderRadius": "5px",
            "fontFamily": "monospace", "fontSize": "12px", "maxHeight": "400px", "overflowY": "scroll",
        }), "系统日志"),
        _panel(html.Div("交易记录..."), "交易记录"),
    ])
