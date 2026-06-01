"""
QuantEngine Pro - 现代化交易系统仪表盘
========================================
侧边栏导航，集成全部功能，无需手动执行 Python 脚本。

功能面板:
  总览 - KPI 卡片 + 权益曲线 + 持仓 + 交易记录
  回测 - 策略/参数配置 → 一键运行 → 结果可视化
  策略 - 16 个内置策略详情与参数配置
  交易 - 实盘执行器启停与控制
  AI分析 - 新闻情感、AI推荐、信号
  数据 - 行情数据一键下载
  日志 - 系统日志与交易记录
  设置 - API 密钥配置与系统信息
"""

import json
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, dcc, html

_backtest_engine_ref = None
_strategy_registry_ref = None
_market_overview_ref = None
_live_executor_ref = None
_llm_service_ref = None


def set_globals(backtest_engine=None, strategy_registry=None,
                market_overview=None, live_executor=None, llm_service=None):
    global _backtest_engine_ref, _strategy_registry_ref
    global _market_overview_ref, _live_executor_ref, _llm_service_ref
    _backtest_engine_ref = backtest_engine
    _strategy_registry_ref = strategy_registry
    _market_overview_ref = market_overview
    _live_executor_ref = live_executor
    _llm_service_ref = llm_service


COLORS = {
    "bg_base": "#060a12",
    "bg_card": "rgba(12,18,30,0.85)",
    "bg_card_hover": "#151d2e",
    "bg_sidebar": "#080d18",
    "bg_input": "#0e1525",
    "border": "rgba(30,41,59,0.5)",
    "border_hover": "rgba(99,102,241,0.3)",
    "text_primary": "#eef2f7",
    "text_secondary": "#8b9ab8",
    "text_muted": "#5a6a84",
    "accent": "#6366f1",
    "accent_hover": "#818cf8",
    "accent_glow": "rgba(99,102,241,0.12)",
    "success": "#34d399",
    "danger": "#f87171",
    "warning": "#fbbf24",
    "info": "#22d3ee",
    "profit": "#34d399",
    "loss": "#f87171",
    "gradient_start": "#6366f1",
    "gradient_end": "#a855f7",
}

SIDEBAR_WIDTH = 240

NAV_ITEMS = [
    {"id": "overview",  "icon": "📊", "label": "总览"},
    {"id": "backtest",  "icon": "📈", "label": "回测"},
    {"id": "strategies","icon": "📋", "label": "策略"},
    {"id": "trading",   "icon": "💹", "label": "交易"},
    {"id": "ai",        "icon": "🤖", "label": "AI分析"},
    {"id": "data",      "icon": "📡", "label": "数据"},
    {"id": "logs",      "icon": "📝", "label": "日志"},
    {"id": "settings",  "icon": "⚙️", "label": "设置"},
]

FONT_UI = "'DM Sans', 'Noto Sans SC', sans-serif"
FONT_MONO = "'JetBrains Mono', 'Fira Code', monospace"

STRATEGY_OPTIONS = [
    {"label": "Dual Thrust - 区间突破", "value": "dual_thrust"},
    {"label": "Turtle - 海龟交易", "value": "turtle"},
    {"label": "Bollinger - 布林带均值回归", "value": "bollinger"},
    {"label": "Dual MA - 双均线", "value": "dual_ma"},
    {"label": "R Breaker - 关键价位", "value": "r_breaker"},
    {"label": "Grid+MA - 网格均线", "value": "grid_ma"},
    {"label": "Simple MM - 做市商", "value": "simple_mm"},
    {"label": "Panic Reversal - 恐慌反转", "value": "panic_reversal"},
    {"label": "Low Vol Defense - 低波防御", "value": "low_vol_defense"},
    {"label": "Multi Factor - 多因子选股", "value": "multi_factor"},
    {"label": "Sector Rotation - 行业轮动", "value": "sector_rotation"},
    {"label": "Aberration - 波动率通道", "value": "aberration"},
    {"label": "Pivot Point - 枢轴点", "value": "pivot_point"},
    {"label": "Fei Ali - 菲阿里四价", "value": "fei_ali"},
    {"label": "Dynamic Breakout II - 动态突破", "value": "dynamic_breakout_ii"},
    {"label": "RSI Reversal - RSI反转", "value": "rsi_reversal"},
]

TF_OPTIONS = [
    {"label": "1 分钟", "value": "1m"},
    {"label": "5 分钟", "value": "5m"},
    {"label": "15 分钟", "value": "15m"},
    {"label": "30 分钟", "value": "30m"},
    {"label": "1 小时", "value": "1h"},
    {"label": "4 小时", "value": "4h"},
    {"label": "1 天", "value": "1d"},
    {"label": "1 周", "value": "1w"},
]

STRATEGY_DETAILS = [
    ("dual_thrust", "Dual Thrust", "区间突破", "经典突破策略，基于前 N 日最高/最低价计算突破区间，K1/K2 参数控制突破敏感度。"),
    ("turtle", "Turtle", "趋势跟踪", "海龟交易策略，唐奇安通道突破入场，ATR 浮动止损，趋势跟踪经典之作。"),
    ("bollinger", "Bollinger", "均值回归", "布林带上下轨触发反转信号，RSI 过滤确认，适合震荡行情。"),
    ("dual_ma", "Dual MA", "趋势跟踪", "双均线金叉死叉信号，配合网格仓位管理，简单有效。"),
    ("r_breaker", "R Breaker", "突破/反转", "基于前日价格的 6 级关键价位系统，突破与反转双向交易。"),
    ("grid_ma", "Grid+MA", "网格交易", "MA 趋势方向过滤 + 网格分层建仓，下跌加仓上涨减仓。"),
    ("simple_mm", "Simple MM", "做市商", "中间价双侧挂限价单，赚取买卖价差，适合低波动品种。"),
    ("panic_reversal", "Panic Reversal", "恐慌反转", "检测恐慌性下跌 + 成交量飙升 + RSI 恢复确认，情绪反转入场。"),
    ("low_vol_defense", "Low Vol Defense", "波动防御", "高波动率自动减仓至 50%，低波动率恢复正常仓位。"),
    ("multi_factor", "Multi Factor", "多因子选股", "动量 + 波动率 + RSI + MACD 多因子等权打分，选择综合得分最高的标的。"),
    ("sector_rotation", "Sector Rotation", "行业轮动", "计算各板块动量强度，定期调仓至动量最强的板块。"),
    ("aberration", "Aberration", "波动率通道", "布林带自适应通道，价格触及外轨反向开仓，回归中轨止盈。"),
    ("pivot_point", "Pivot Point", "枢轴点", "经典日内枢轴点系统，S1/S2 支撑买入，R1/R2 阻力卖出。"),
    ("fei_ali", "Fei Ali", "四价突破", "基于昨高/昨低/昨收/昨开的四价突破系统，突破关键价位入场。"),
    ("dynamic_breakout_ii", "Dynamic Breakout II", "动态突破", "ATR 动态调整回溯周期，高波动时快速反应，低波动时稳定持仓。"),
    ("rsi_reversal", "RSI Reversal", "RSI反转", "RSI 超买超卖阈值反转交易，超卖买入超买卖出。"),
]

DOWNLOAD_SYMBOLS = [
    {"label": "BTC/USDT", "value": "BTC/USDT"},
    {"label": "ETH/USDT", "value": "ETH/USDT"},
    {"label": "SOL/USDT", "value": "SOL/USDT"},
]

DOWNLOAD_MARKETS = [
    {"label": "加密货币", "value": "crypto"},
    {"label": "A 股", "value": "a_share"},
]


def _card_style():
    return {
        "backgroundColor": "rgba(12,18,30,0.85)",
        "border": "1px solid rgba(30,41,59,0.5)",
        "borderRadius": "14px",
        "padding": "24px",
        "backdropFilter": "blur(12px)",
        "boxShadow": "0 4px 32px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.03)",
    }


def _kpi_card(title: str, value: str, subtitle: str = "",
              color: str = COLORS["text_primary"],
              icon: str = "", delta: str = "") -> html.Div:
    delta_color = COLORS["success"] if delta.startswith("+") else COLORS["danger"] if delta.startswith("-") else COLORS["text_muted"]
    delta_bg = "rgba(52,211,153,0.12)" if delta.startswith("+") else "rgba(248,113,113,0.12)" if delta.startswith("-") else "rgba(90,106,132,0.12)"
    return html.Div([
        html.Div([
            html.Span(icon, style={"fontSize": "18px"}) if icon else None,
            html.Span(title, style={
                "fontSize": "11px", "color": COLORS["text_muted"],
                "textTransform": "uppercase", "letterSpacing": "0.8px",
                "fontWeight": "600",
            }),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        html.Div(value, style={
            "fontSize": "26px", "fontWeight": "700",
            "color": color, "marginTop": "10px",
            "fontFamily": FONT_MONO, "lineHeight": "1.1",
        }),
        html.Div([
            html.Span(delta, style={
                "fontSize": "11px", "fontWeight": "600",
                "color": delta_color,
                "background": delta_bg,
                "padding": "2px 8px", "borderRadius": "8px",
            }) if delta else None,
            html.Span(subtitle, style={"fontSize": "11px", "color": COLORS["text_muted"]}),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginTop": "8px"}),
    ], style={
        **_card_style(),
        "position": "relative",
        "overflow": "hidden",
        "transition": "transform 0.2s cubic-bezier(.4,0,.2,1), box-shadow 0.2s",
    })


def _section(title: str, icon: str = "", children=None) -> html.Div:
    header = html.Div([
        html.Span(icon, style={"fontSize": "15px"}) if icon else None,
        html.H3(title, style={
            "fontSize": "13px", "fontWeight": "600",
            "color": COLORS["text_primary"], "margin": 0,
            "textTransform": "uppercase", "letterSpacing": "0.8px",
        }),
    ], style={"display": "flex", "alignItems": "center", "gap": "8px",
               "marginBottom": "16px", "paddingBottom": "12px",
               "borderBottom": "1px solid rgba(30,41,59,0.4)"})
    content = [header]
    if isinstance(children, list):
        content.extend(children)
    elif children is not None:
        content.append(children)
    return html.Div(content, style={
        **_card_style(),
        "marginBottom": "16px",
    })


def _ticker_item(label: str, price_id: str, change_id: str) -> html.Div:
    return html.Div([
        html.Span(label, style={
            "fontSize": "12px", "fontWeight": "500",
            "color": COLORS["text_secondary"], "marginRight": "4px",
        }),
        html.Span(id=price_id, children="...", style={
            "fontSize": "15px", "fontWeight": "700",
            "color": COLORS["text_primary"],
            "fontFamily": FONT_MONO,
        }),
        html.Span(id=change_id, children="", style={
            "fontSize": "11px", "fontWeight": "500", "marginLeft": "4px",
        }),
    ], style={"display": "flex", "alignItems": "center"})


def _empty_chart(title: str = "", height: int = 320) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title={"text": title, "font": {"color": COLORS["text_muted"], "size": 13}},
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COLORS["text_secondary"], "size": 11},
        margin=dict(l=40, r=20, t=40, b=40),
        height=height,
        xaxis={"gridcolor": "rgba(255,255,255,0.03)", "showgrid": True},
        yaxis={"gridcolor": "rgba(255,255,255,0.03)", "showgrid": True},
    )
    return fig


def _btn(text: str, id: str, primary: bool = True, full: bool = False) -> html.Button:
    if primary:
        bg = f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})"
        border = "none"
        color = "#fff"
    else:
        bg = COLORS["bg_input"]
        border = f"1px solid {COLORS['border']}"
        color = COLORS["text_primary"]
    return html.Button(text, id=id, n_clicks=0, style={
        "padding": "10px 24px",
        "borderRadius": "10px",
        "border": border,
        "fontSize": "14px",
        "fontWeight": "500",
        "cursor": "pointer",
        "transition": "all 0.2s",
        "width": "100%" if full else "auto",
        "background": bg,
        "color": color,
        "fontFamily": FONT_UI,
    })


def _input_field(label: str, id: str, value: str = "",
                 type: str = "text", options: list = None) -> html.Div:
    input_style = {
        "width": "100%", "padding": "10px 14px",
        "borderRadius": "10px", "border": f"1px solid {COLORS['border']}",
        "backgroundColor": COLORS["bg_input"],
        "color": COLORS["text_primary"],
        "fontSize": "13px", "outline": "none",
        "fontFamily": FONT_UI,
        "transition": "border-color 0.2s",
    }
    control = dcc.Input(
        id=id, type=type, value=value,
        style=input_style,
    ) if options is None else dcc.Dropdown(
        id=id, options=options, value=value,
        style={
            "color": "#000",
            "borderRadius": "10px",
        },
    )
    return html.Div([
        html.Label(label, style={
            "fontSize": "11px", "fontWeight": "600",
            "color": COLORS["text_secondary"],
            "textTransform": "uppercase",
            "letterSpacing": "0.5px",
            "marginBottom": "6px", "display": "block",
        }),
        control,
    ], style={"marginBottom": "12px"})


def _data_table(headers: list, rows: list, empty_msg: str = "暂无数据") -> html.Div:
    if not rows:
        return html.Div(empty_msg, style={
            "color": COLORS["text_muted"], "textAlign": "center",
            "padding": "20px", "fontSize": "13px",
        })

    header_row = html.Tr([
        html.Th(h, style={
            "padding": "10px 14px", "fontSize": "11px",
            "color": COLORS["text_muted"], "textAlign": "left",
            "borderBottom": f"1px solid {COLORS['border']}",
            "textTransform": "uppercase", "letterSpacing": "0.5px",
        }) for h in headers
    ])

    body_rows = []
    for i, row in enumerate(rows):
        bg = "rgba(255,255,255,0.02)" if i % 2 == 0 else "transparent"
        body_rows.append(html.Tr(row, style={"backgroundColor": bg}))

    return html.Div([
        html.Table([
            html.Thead(header_row),
            html.Tbody(body_rows),
        ], style={"width": "100%", "borderCollapse": "collapse"}),
    ])


def _sidebar() -> html.Div:
    nav_links = []
    for i, item in enumerate(NAV_ITEMS):
        nav_links.append(
            html.Button(
                f"{item['icon']}  {item['label']}",
                id=f"nav-{item['id']}",
                n_clicks=0,
                className="nav-btn active" if i == 0 else "nav-btn",
            )
        )

    return html.Div([
        html.Div([
            html.Div("⚡", style={"fontSize": "26px"}),
            html.Div([
                html.Div("量化引擎", style={
                    "fontSize": "17px", "fontWeight": "700",
                    "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                    "WebkitBackgroundClip": "text",
                    "WebkitTextFillColor": "transparent",
                    "lineHeight": "1.2",
                }),
                html.Div("专业版", style={
                    "fontSize": "10px", "color": COLORS["text_muted"],
                    "letterSpacing": "2.5px", "textTransform": "uppercase",
                }),
            ]),
        ], style={
            "padding": "24px 20px 28px",
            "display": "flex", "alignItems": "center", "gap": "12px",
            "borderBottom": f"1px solid {COLORS['border']}",
        }),

        html.Div(nav_links, style={"padding": "12px 0", "flex": "1"}),

        html.Div([
            html.Div([
                html.Span("●", style={
                    "color": COLORS["success"], "fontSize": "7px",
                    "animation": "pulse 2s ease-in-out infinite",
                }),
                html.Span("系统运行中", style={
                    "fontSize": "11px", "color": COLORS["text_muted"],
                }),
            ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
            html.Div("v0.1.0", style={
                "fontSize": "11px", "color": COLORS["text_muted"],
                "fontFamily": FONT_MONO,
            }),
        ], style={
            "textAlign": "center", "padding": "16px 20px",
            "borderTop": f"1px solid {COLORS['border']}",
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "center",
        }),
    ], style={
        "position": "fixed", "left": 0, "top": 0,
        "width": f"{SIDEBAR_WIDTH}px", "height": "100vh",
        "backgroundColor": COLORS["bg_sidebar"],
        "borderRight": f"1px solid {COLORS['border']}",
        "display": "flex", "flexDirection": "column",
        "zIndex": 100,
        "backdropFilter": "blur(8px)",
    })


def _header() -> html.Div:
    return html.Div([
        html.Div([
            html.Div(id="page-title", style={
                "fontSize": "22px", "fontWeight": "700",
                "color": COLORS["text_primary"],
                "fontFamily": FONT_UI,
                "letterSpacing": "-0.3px",
            }),
            html.Div([
                html.Div(id="live-clock", style={
                    "fontSize": "13px", "color": COLORS["text_muted"],
                    "fontFamily": FONT_MONO,
                }),
                html.Div([
                    html.Span("●", style={
                        "color": COLORS["success"], "fontSize": "7px",
                        "animation": "pulse 2s ease-in-out infinite",
                    }),
                    html.Span("系统运行中", style={
                        "fontSize": "12px", "color": COLORS["text_secondary"],
                    }),
                ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
            ], style={"display": "flex", "alignItems": "center", "gap": "20px"}),
        ], style={
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "center",
            "marginBottom": "10px",
        }),

        html.Div(id="ticker-bar", style={
            "display": "flex", "alignItems": "center", "gap": "16px",
            "padding": "10px 16px",
            "background": "rgba(6,10,18,0.6)",
            "borderRadius": "12px",
            "border": f"1px solid {COLORS['border']}",
            "minHeight": "36px",
            "fontSize": "13px",
            "color": COLORS["text_muted"],
        }),
    ], style={
        "padding": "16px 28px 0",
        "borderBottom": f"1px solid {COLORS['border']}",
        "backgroundColor": "rgba(12,18,30,0.6)",
        "backdropFilter": "blur(8px)",
    })


def _page_overview() -> html.Div:
    return html.Div([
        html.Div([
            _kpi_card("总资产", "¥100,000.00", "初始资金 ¥100,000",
                      icon="💰", delta="+0.00%"),
            _kpi_card("当日盈亏", "¥0.00", "未实现",
                      color=COLORS["profit"], icon="📈", delta="+0.00%"),
            _kpi_card("最大回撤", "0.00%", "当前回撤 0.00%",
                      color=COLORS["text_primary"], icon="📉"),
            _kpi_card("夏普比率", "—", "年化 0.00%",
                      color=COLORS["info"], icon="🎯"),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
            "gap": "16px", "marginBottom": "24px",
        }),

        _section("权益曲线", icon="📊",
            children=dcc.Graph(
                id="overview-equity-chart",
                figure=_empty_chart("暂无回测数据，请前往「回测」页面运行"),
                style={"height": "360px"},
                config={"displayModeBar": False},
            ),
        ),

        html.Div([
            _section("当前持仓", icon="💼",
                children=html.Div(id="overview-positions",
                    children=[
                        html.Div("暂无持仓", style={
                            "color": COLORS["text_muted"],
                            "textAlign": "center", "padding": "40px 0",
                            "fontSize": "13px",
                        }),
                    ],
                ),
            ),
            _section("最近交易", icon="🔄",
                children=html.Div(id="overview-trades",
                    children=[
                        html.Div("暂无交易记录", style={
                            "color": COLORS["text_muted"],
                            "textAlign": "center", "padding": "40px 0",
                            "fontSize": "13px",
                        }),
                    ],
                ),
            ),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gap": "16px",
        }),
    ])


def _page_backtest() -> html.Div:
    return html.Div([
        _section("回测配置", icon="⚙️", children=[
            html.Div([
                _input_field("策略", "bt-strategy", "dual_thrust",
                             options=STRATEGY_OPTIONS),
                _input_field("交易对", "bt-symbol", "ETH/USDT"),
                _input_field("周期", "bt-timeframe", "1h", options=TF_OPTIONS),
                _input_field("初始资金 (USDT)", "bt-capital", "100000", type="number"),
                _input_field("市场", "bt-market", "crypto",
                             options=[
                                 {"label": "加密货币", "value": "crypto"},
                                 {"label": "A股", "value": "a_share"},
                             ]),
            ], style={"display": "grid",
                      "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))",
                      "gap": "12px"}),
            html.Div([
                html.Button("▶ 运行回测", id="bt-run-btn", n_clicks=0, style={
                    "padding": "12px 32px",
                    "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                    "color": "#fff", "border": "none", "borderRadius": "10px",
                    "fontSize": "15px", "fontWeight": "600",
                    "cursor": "pointer", "transition": "all 0.25s ease",
                    "display": "flex", "alignItems": "center", "gap": "8px",
                    "fontFamily": FONT_UI,
                    "boxShadow": f"0 4px 16px {COLORS['accent_glow']}",
                }),
                html.Div(id="bt-status", style={
                    "fontSize": "13px", "color": COLORS["text_muted"],
                    "marginLeft": "16px", "display": "flex",
                    "alignItems": "center", "gap": "8px",
                }),
            ], style={"display": "flex", "alignItems": "center",
                       "marginTop": "16px"}),
        ]),

        html.Div(id="bt-progress", style={"display": "none"},
            children=[
                html.Div(style={
                    "height": "4px", "borderRadius": "2px",
                    "background": f"linear-gradient(90deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                    "animation": "progress 2s ease-in-out infinite",
                }),
            ]
        ),

        html.Div(id="bt-results", style={"display": "none"}),
    ])


def _build_backtest_results(report: Dict) -> html.Div:
    if not report or "error" in report:
        return html.Div([
            html.Div("⚠️ 回测失败", style={
                "fontSize": "16px", "fontWeight": "600",
                "color": COLORS["danger"], "marginBottom": "8px",
            }),
            html.Div(str(report.get("error", "未知错误")), style={
                "color": COLORS["text_secondary"], "fontSize": "13px",
            }),
        ])

    return html.Div([
        html.Div([
            _kpi_card("总收益率",
                f"{report.get('total_return_pct', 0):+.2f}%",
                color=COLORS["profit"] if report.get('total_return_pct', 0) >= 0 else COLORS["danger"],
                icon="📊"),
            _kpi_card("年化收益率",
                f"{report.get('annual_return_pct', 0):+.2f}%",
                color=COLORS["profit"] if report.get('annual_return_pct', 0) >= 0 else COLORS["danger"],
                icon="📈"),
            _kpi_card("夏普比率",
                f"{report.get('sharpe_ratio', 0):.2f}",
                color=COLORS["info"], icon="🎯"),
            _kpi_card("最大回撤",
                f"{report.get('max_drawdown_pct', 0):.2f}%",
                color=COLORS["danger"], icon="📉"),
            _kpi_card("总交易次数",
                f"{report.get('total_trades', 0)}",
                icon="🔄"),
            _kpi_card("胜率",
                f"{report.get('win_rate_pct', 0):.1f}%",
                icon="✅"),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(170px, 1fr))",
            "gap": "12px", "marginBottom": "20px",
        }),

        _section("权益曲线", icon="📊",
            children=dcc.Graph(
                figure=_build_equity_figure(report),
                style={"height": "320px"},
                config={"displayModeBar": False},
            ),
        ),

        _section("交易明细", icon="📋",
            children=_build_trades_table(report),
        ),
    ])


def _build_equity_figure(report: Dict) -> go.Figure:
    fig = go.Figure()

    equity = report.get("equity_curve", [])
    if equity:
        dates = [e[0] for e in equity]
        values = [e[1] for e in equity]
        fig.add_trace(go.Scatter(
            x=dates, y=values,
            mode="lines", name="权益",
            line=dict(color=COLORS["accent"], width=2),
            fill="tozeroy",
            fillcolor=COLORS["accent_glow"],
        ))

        init = report.get("initial_capital", values[0]) if values else 0
        fig.add_hline(y=init, line_dash="dash",
                      line_color=COLORS["text_muted"],
                      annotation_text=f"初始 {init:,.0f}",
                      annotation_font_size=11)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COLORS["text_secondary"], "size": 11},
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis={"gridcolor": "rgba(255,255,255,0.03)"},
        yaxis={"gridcolor": "rgba(255,255,255,0.03)",
               "tickformat": ","},
        hovermode="x unified",
        showlegend=False,
    )
    return fig


def _build_trades_table(report: Dict) -> html.Div:
    trades = report.get("trades", [])
    if not trades:
        return html.Div("暂无交易记录", style={
            "color": COLORS["text_muted"], "textAlign": "center",
            "padding": "20px", "fontSize": "13px",
        })

    rows = []
    for i, t in enumerate(trades[-50:]):
        pnl = t.get("pnl", 0)
        bg = "rgba(255,255,255,0.02)" if i % 2 == 0 else "transparent"
        rows.append(html.Tr([
            html.Td(t.get("symbol", ""),
                    style={"padding": "8px 14px", "fontSize": "12px", "fontFamily": FONT_MONO}),
            html.Td("买入" if t.get("side") in ("BUY", "buy") else "卖出",
                    style={"padding": "8px 14px", "fontSize": "12px",
                           "color": COLORS["profit"] if t.get("side") in ("BUY", "buy") else COLORS["danger"],
                           "fontWeight": "600"}),
            html.Td(f"{t.get('quantity', 0):.4f}",
                    style={"padding": "8px 14px", "fontSize": "12px", "fontFamily": FONT_MONO, "textAlign": "right"}),
            html.Td(f"{t.get('entry_price', 0):.2f}",
                    style={"padding": "8px 14px", "fontSize": "12px", "fontFamily": FONT_MONO, "textAlign": "right"}),
            html.Td(f"{t.get('exit_price', 0):.2f}",
                    style={"padding": "8px 14px", "fontSize": "12px", "fontFamily": FONT_MONO, "textAlign": "right"}),
            html.Td(f"{pnl:+.2f}",
                    style={"padding": "8px 14px", "fontSize": "12px",
                           "color": COLORS["profit"] if pnl >= 0 else COLORS["danger"],
                           "fontWeight": "600", "fontFamily": FONT_MONO, "textAlign": "right"}),
        ], style={"backgroundColor": bg}))

    return html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th("标的", style={"padding": "10px 14px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "left",
                          "borderBottom": f"1px solid {COLORS['border']}",
                          "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                html.Th("方向", style={"padding": "10px 14px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "left",
                          "borderBottom": f"1px solid {COLORS['border']}",
                          "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                html.Th("数量", style={"padding": "10px 14px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}",
                          "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                html.Th("入场价", style={"padding": "10px 14px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}",
                          "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                html.Th("出场价", style={"padding": "10px 14px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}",
                          "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                html.Th("盈亏", style={"padding": "10px 14px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}",
                          "textTransform": "uppercase", "letterSpacing": "0.5px"}),
            ])),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse"}),
        html.Div(f"共 {len(trades)} 笔交易，仅显示最近 50 笔",
                 style={"color": COLORS["text_muted"], "fontSize": "11px",
                        "textAlign": "right", "padding": "8px 14px"}),
    ])


def _page_strategies() -> html.Div:
    cards = []
    for sid, name, stype, desc in STRATEGY_DETAILS:
        cards.append(
            html.Div([
                html.Div([
                    html.Span(stype, style={
                        "fontSize": "11px", "fontWeight": "600",
                        "padding": "3px 12px", "borderRadius": "10px",
                        "background": COLORS["accent_glow"],
                        "color": COLORS["accent"],
                        "letterSpacing": "0.5px",
                    }),
                ], style={"marginBottom": "10px"}),
                html.H4(name, style={
                    "fontSize": "15px", "fontWeight": "600",
                    "color": COLORS["text_primary"], "margin": "0 0 8px 0",
                }),
                html.P(desc, style={
                    "fontSize": "12px", "color": COLORS["text_secondary"],
                    "lineHeight": "1.7", "margin": 0,
                }),
            ], style={
                **_card_style(),
                "transition": "all 0.25s ease",
            })
        )

    return html.Div([
        html.Div(f"共 {len(STRATEGY_DETAILS)} 个内置策略", style={
            "fontSize": "13px", "color": COLORS["text_muted"],
            "marginBottom": "16px",
        }),
        html.Div(cards, style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fill, minmax(280px, 1fr))",
            "gap": "16px",
        }),
    ])


def _page_trading() -> html.Div:
    return html.Div([
        html.Div([
            _kpi_card("运行状态", "已停止", icon="⏹️",
                      color=COLORS["warning"]),
            _kpi_card("扫描周期", "10 秒", icon="⏱️"),
            _kpi_card("活跃策略", "0", icon="📋"),
            _kpi_card("今日信号", "0", icon="📡"),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))",
            "gap": "16px", "marginBottom": "24px",
        }),
        _section("执行器控制", icon="🎮",
            children=html.Div([
                html.Div("实盘执行器当前未运行。配置 API Key 并连接券商后可启动。",
                         style={"color": COLORS["text_muted"], "fontSize": "13px",
                                "marginBottom": "16px", "lineHeight": "1.6"}),
                html.Div([
                    html.Button("▶ 启动执行器", id="exec-start-btn",
                                n_clicks=0, style={
                        "padding": "10px 24px",
                        "background": f"linear-gradient(135deg, {COLORS['success']}, #16a34a)",
                        "color": "#fff", "border": "none", "borderRadius": "10px",
                        "fontSize": "14px", "fontWeight": "500", "cursor": "pointer",
                        "transition": "all 0.25s ease",
                        "fontFamily": FONT_UI,
                    }),
                    html.Button("⏹ 停止执行器", id="exec-stop-btn",
                                n_clicks=0, style={
                        "padding": "10px 24px",
                        "background": f"linear-gradient(135deg, {COLORS['danger']}, #dc2626)",
                        "color": "#fff", "border": "none", "borderRadius": "10px",
                        "fontSize": "14px", "fontWeight": "500", "cursor": "pointer",
                        "marginLeft": "10px",
                        "transition": "all 0.25s ease",
                        "fontFamily": FONT_UI,
                    }),
                ], style={"display": "flex", "alignItems": "center"}),
                html.Div(id="exec-status-text", style={
                    "fontSize": "13px", "color": COLORS["text_muted"],
                    "marginTop": "12px",
                }),
            ]),
        ),
        _section("当前持仓", icon="💼",
            children=html.Div("暂无持仓", style={
                "color": COLORS["text_muted"], "textAlign": "center",
                "padding": "40px 0", "fontSize": "13px",
            }),
        ),
    ])


def _page_ai() -> html.Div:
    return html.Div([
        _section("AI 新闻情感分析", icon="🧠",
            children=html.Div([
                html.Div([
                    html.Button("📰 获取最新新闻并分析", id="ai-fetch-btn",
                               n_clicks=0, style={
                                   "padding": "10px 24px", "borderRadius": "10px",
                                   "border": "none",
                                   "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                                   "color": "#fff", "fontSize": "13px",
                                   "fontWeight": "500", "cursor": "pointer",
                                   "transition": "all 0.25s ease",
                                   "fontFamily": FONT_UI,
                                   "boxShadow": f"0 4px 16px {COLORS['accent_glow']}",
                               }),
                    html.Span(id="ai-status", children="点击按钮获取最新新闻与 AI 分析",
                             style={"color": COLORS["text_muted"], "fontSize": "12px",
                                    "marginLeft": "12px"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "16px"}),
                dcc.Graph(
                    id="ai-sentiment-chart",
                    figure=_empty_chart("点击「获取最新新闻并分析」查看情感趋势", height=300),
                    config={"displayModeBar": False},
                ),
                html.Div(id="ai-news-list", style={"marginTop": "12px"}),
            ]),
        ),
        html.Div([
            _section("AI 推荐", icon="⭐",
                children=html.Div(id="ai-picks", children=[
                    html.Div("点击左侧按钮获取 AI 推荐", style={
                        "color": COLORS["text_muted"], "textAlign": "center",
                        "padding": "40px 0", "fontSize": "13px",
                    }),
                ]),
            ),
            _section("信号推荐", icon="🔔",
                children=html.Div(id="ai-signals", children=[
                    html.Div("AI 分析完成后将在此显示交易信号", style={
                        "color": COLORS["text_muted"], "textAlign": "center",
                        "padding": "40px 0", "fontSize": "13px",
                    }),
                ]),
            ),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}),
    ])


def _page_data() -> html.Div:
    return html.Div([
        _section("数据下载", icon="📥", children=[
            html.Div([
                _input_field("市场", "dl-market", "crypto", options=DOWNLOAD_MARKETS),
                _input_field("交易对", "dl-symbols", "BTC/USDT", options=DOWNLOAD_SYMBOLS),
                _input_field("周期", "dl-freq", "1h", options=TF_OPTIONS),
                _input_field("最大数量", "dl-limit", "500", type="number"),
            ], style={"display": "grid",
                      "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))",
                      "gap": "12px"}),
            html.Div([
                html.Button("⬇ 开始下载", id="dl-run-btn", n_clicks=0, style={
                    "padding": "12px 32px",
                    "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                    "color": "#fff", "border": "none", "borderRadius": "10px",
                    "fontSize": "15px", "fontWeight": "600",
                    "cursor": "pointer", "transition": "all 0.25s ease",
                    "fontFamily": FONT_UI,
                    "boxShadow": f"0 4px 16px {COLORS['accent_glow']}",
                }),
                html.Div(id="dl-status", style={
                    "fontSize": "13px", "color": COLORS["text_muted"],
                    "marginLeft": "16px", "display": "inline-flex",
                    "alignItems": "center", "gap": "8px",
                }),
            ], style={"display": "flex", "alignItems": "center",
                       "marginTop": "16px"}),
        ]),
        _section("已缓存数据", icon="💾",
            children=html.Div([
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("数据源", style={"padding": "10px 14px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "left",
                                  "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                        html.Th("交易对/代码", style={"padding": "10px 14px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "left",
                                  "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                        html.Th("周期", style={"padding": "10px 14px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "left",
                                  "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                        html.Th("条数", style={"padding": "10px 14px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "right",
                                  "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                        html.Th("更新时间", style={"padding": "10px 14px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "right",
                                  "textTransform": "uppercase", "letterSpacing": "0.5px"}),
                    ])),
                    html.Tbody(id="dl-cache-table",
                        children=[html.Tr([
                            html.Td("暂无数据", colSpan=5,
                                    style={"textAlign": "center", "padding": "20px",
                                           "color": COLORS["text_muted"], "fontSize": "13px"}),
                        ])]),
                ], style={"width": "100%", "borderCollapse": "collapse"}),
            ]),
        ),
    ])


def _page_logs() -> html.Div:
    return html.Div([
        _section("系统日志", icon="📝",
            children=html.Div(id="logs-system", style={
                "fontFamily": FONT_MONO,
                "fontSize": "12px", "lineHeight": "1.8",
                "maxHeight": "500px", "overflowY": "scroll",
            }, children=[
                html.Div(datetime.now().strftime("[%H:%M:%S] 系统就绪"),
                         style={"color": COLORS["text_secondary"]}),
            ]),
        ),
        _section("交易记录", icon="🔄",
            children=html.Div(id="logs-trades",
                children=[html.Div("暂无交易记录", style={
                    "color": COLORS["text_muted"], "textAlign": "center",
                    "padding": "40px 0", "fontSize": "13px",
                })]),
        ),
    ])


def _page_settings() -> html.Div:
    return html.Div([
        _section("API 密钥配置", icon="🔑", children=[
            html.Div([
                html.Div([
                    html.Label("DeepSeek API Key", style={
                        "fontSize": "13px", "fontWeight": "600",
                        "color": COLORS["text_primary"], "marginBottom": "6px",
                        "display": "block",
                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                    }),
                    html.Div([
                        dcc.Input(id="cfg-deepseek-key", type="password",
                                  placeholder="sk-...",
                                  style={
                                      "flex": "1", "padding": "10px 14px",
                                      "borderRadius": "10px", "border": f"1px solid {COLORS['border']}",
                                      "background": COLORS["bg_input"],
                                      "color": COLORS["text_primary"], "fontSize": "14px",
                                      "outline": "none", "fontFamily": FONT_MONO,
                                  }),
                        html.Button("保存", id="save-deepseek-key", n_clicks=0,
                                   style={
                                       "padding": "10px 20px", "borderRadius": "10px",
                                       "border": "none",
                                       "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                                       "color": "#fff", "fontSize": "13px",
                                       "cursor": "pointer", "whiteSpace": "nowrap",
                                       "fontFamily": FONT_UI,
                                   }),
                    ], style={"display": "flex", "gap": "8px"}),
                    html.Div(id="deepseek-key-status", style={
                        "fontSize": "12px", "color": COLORS["text_muted"],
                        "marginTop": "6px",
                    }),
                ], style={"marginBottom": "20px"}),

                html.Div([
                    html.Label("OpenAI API Key（可选）", style={
                        "fontSize": "13px", "fontWeight": "600",
                        "color": COLORS["text_primary"], "marginBottom": "6px",
                        "display": "block",
                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                    }),
                    html.Div([
                        dcc.Input(id="cfg-openai-key", type="password",
                                  placeholder="sk-...",
                                  style={
                                      "flex": "1", "padding": "10px 14px",
                                      "borderRadius": "10px", "border": f"1px solid {COLORS['border']}",
                                      "background": COLORS["bg_input"],
                                      "color": COLORS["text_primary"], "fontSize": "14px",
                                      "outline": "none", "fontFamily": FONT_MONO,
                                  }),
                        html.Button("保存", id="save-openai-key", n_clicks=0,
                                   style={
                                       "padding": "10px 20px", "borderRadius": "10px",
                                       "border": "none",
                                       "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                                       "color": "#fff", "fontSize": "13px",
                                       "cursor": "pointer", "whiteSpace": "nowrap",
                                       "fontFamily": FONT_UI,
                                   }),
                    ], style={"display": "flex", "gap": "8px"}),
                    html.Div(id="openai-key-status", style={
                        "fontSize": "12px", "color": COLORS["text_muted"],
                        "marginTop": "6px",
                    }),
                ], style={"marginBottom": "20px"}),

                html.Div([
                    html.Label("Anthropic API Key（可选）", style={
                        "fontSize": "13px", "fontWeight": "600",
                        "color": COLORS["text_primary"], "marginBottom": "6px",
                        "display": "block",
                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                    }),
                    html.Div([
                        dcc.Input(id="cfg-anthropic-key", type="password",
                                  placeholder="sk-ant-...",
                                  style={
                                      "flex": "1", "padding": "10px 14px",
                                      "borderRadius": "10px", "border": f"1px solid {COLORS['border']}",
                                      "background": COLORS["bg_input"],
                                      "color": COLORS["text_primary"], "fontSize": "14px",
                                      "outline": "none", "fontFamily": FONT_MONO,
                                  }),
                        html.Button("保存", id="save-anthropic-key", n_clicks=0,
                                   style={
                                       "padding": "10px 20px", "borderRadius": "10px",
                                       "border": "none",
                                       "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                                       "color": "#fff", "fontSize": "13px",
                                       "cursor": "pointer", "whiteSpace": "nowrap",
                                       "fontFamily": FONT_UI,
                                   }),
                    ], style={"display": "flex", "gap": "8px"}),
                    html.Div(id="anthropic-key-status", style={
                        "fontSize": "12px", "color": COLORS["text_muted"],
                        "marginTop": "6px",
                    }),
                ], style={"marginBottom": "20px"}),

                html.Div([
                    html.Label("数据源配置", style={
                        "fontSize": "13px", "fontWeight": "600",
                        "color": COLORS["text_primary"], "marginBottom": "10px",
                        "display": "block",
                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                    }),
                    html.Div([
                        html.Span("行情数据:", style={"color": COLORS["text_secondary"], "fontSize": "13px"}),
                        html.Span("akshare（A股·免费） + CCXT（加密货币·免费）",
                                 style={"color": COLORS["text_muted"], "fontSize": "12px", "marginLeft": "8px"}),
                    ], style={"marginBottom": "6px"}),
                    html.Div([
                        html.Span("大盘数据:", style={"color": COLORS["text_secondary"], "fontSize": "13px"}),
                        html.Span("EastMoney（免费）",
                                 style={"color": COLORS["text_muted"], "fontSize": "12px", "marginLeft": "8px"}),
                    ], style={"marginBottom": "6px"}),
                    html.Div([
                        html.Span("LLM服务:", style={"color": COLORS["text_secondary"], "fontSize": "13px"}),
                        html.Span("DeepSeek（需 API Key）→ OpenAI/Claude（可选升级）",
                                 style={"color": COLORS["text_muted"], "fontSize": "12px", "marginLeft": "8px"}),
                    ]),
                ], style={
                    "padding": "16px", "borderRadius": "12px",
                    "background": COLORS["bg_base"],
                    "border": f"1px solid {COLORS['border']}",
                }),
            ], style={"maxWidth": "600px"}),
        ]),

        _section("系统信息", icon="ℹ️", children=[
            html.Div([
                html.Div([
                    html.Span("版本:", style={"color": COLORS["text_secondary"], "fontSize": "13px"}),
                    html.Span("0.1.0", style={"color": COLORS["text_primary"], "fontSize": "13px", "marginLeft": "8px", "fontFamily": FONT_MONO}),
                ], style={"marginBottom": "6px"}),
                html.Div([
                    html.Span("Python:", style={"color": COLORS["text_secondary"], "fontSize": "13px"}),
                    html.Span(f"{sys.version.split()[0] if hasattr(sys, 'version') else '3.10+'}",
                             style={"color": COLORS["text_primary"], "fontSize": "13px", "marginLeft": "8px", "fontFamily": FONT_MONO}),
                ], style={"marginBottom": "6px"}),
                html.Div([
                    html.Span("内置策略:", style={"color": COLORS["text_secondary"], "fontSize": "13px"}),
                    html.Span("16个", style={"color": COLORS["text_primary"], "fontSize": "13px", "marginLeft": "8px", "fontFamily": FONT_MONO}),
                ]),
            ]),
        ]),
    ])


def create_dashboard(backtest_engine=None, strategy_registry=None,
                     market_overview=None) -> dash.Dash:
    set_globals(
        backtest_engine=backtest_engine,
        strategy_registry=strategy_registry,
        market_overview=market_overview,
    )

    app = dash.Dash(
        __name__,
        title="量化引擎专业版",
        update_title=None,
    )

    app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
    --bg-base: #060a12;
    --bg-card: rgba(12,18,30,0.85);
    --bg-sidebar: #080d18;
    --bg-input: #0e1525;
    --border: rgba(30,41,59,0.5);
    --border-hover: rgba(99,102,241,0.3);
    --text-primary: #eef2f7;
    --text-secondary: #8b9ab8;
    --text-muted: #5a6a84;
    --accent: #6366f1;
    --accent-hover: #818cf8;
    --accent-glow: rgba(99,102,241,0.12);
    --success: #34d399;
    --danger: #f87171;
    --warning: #fbbf24;
    --info: #22d3ee;
    --gradient-start: #6366f1;
    --gradient-end: #a855f7;
    --radius: 14px;
    --radius-sm: 10px;
    --shadow-card: 0 4px 32px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.03);
    --shadow-glow: 0 0 40px rgba(99,102,241,0.08);
    --font-ui: 'DM Sans', 'Noto Sans SC', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
    --sidebar-w: 240px;
}

* { box-sizing: border-box; }

body {
    background: var(--bg-base);
    font-family: var(--font-ui);
    -webkit-font-smoothing: antialiased;
}

/* ─── Sidebar ─── */
.nav-btn {
    padding: 11px 18px;
    cursor: pointer;
    border-radius: var(--radius-sm);
    margin: 2px 10px;
    font-size: 13.5px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: all 0.2s cubic-bezier(.4,0,.2,1);
    border-left: 3px solid transparent;
    text-decoration: none;
    background: transparent;
    border: none;
    width: calc(var(--sidebar-w) - 20px);
    text-align: left;
    font-family: var(--font-ui);
    color: var(--text-muted);
    position: relative;
    overflow: hidden;
}
.nav-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: var(--radius-sm);
    opacity: 0;
    background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(168,85,247,0.05));
    transition: opacity 0.2s;
}
.nav-btn:hover {
    color: var(--text-secondary);
}
.nav-btn:hover::before {
    opacity: 1;
}
.nav-btn.active {
    background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
    color: #ffffff;
    border-left: 3px solid var(--gradient-end);
    box-shadow: 0 4px 20px rgba(99,102,241,0.2), inset 0 1px 0 rgba(255,255,255,0.1);
    font-weight: 600;
}
.nav-btn.active::before { opacity: 0; }

/* ─── Page transitions ─── */
[id^="page-"] {
    animation: pageFadeIn 0.35s cubic-bezier(.4,0,.2,1);
}
@keyframes pageFadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ─── Cards ─── */
[id^="page-"] > div > div,
[id^="page-"] > div > div > div {
    transition: transform 0.2s, box-shadow 0.2s;
}

/* ─── KPI card gradient border ─── */
[id^="page-"] > div > div:first-child > div {
    position: relative;
}
[id^="page-"] > div > div:first-child > div::after {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    border-radius: 3px;
    background: linear-gradient(180deg, var(--gradient-start), var(--gradient-end));
    opacity: 0.7;
}

/* ─── Section headers ─── */
h3 {
    letter-spacing: 0.8px !important;
}

/* ─── Buttons (primary) ─── */
button[id$="-btn"], button[id$="-run-btn"] {
    position: relative;
    overflow: hidden;
    transition: all 0.2s cubic-bezier(.4,0,.2,1) !important;
}
button[id$="-btn"]:hover, button[id$="-run-btn"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 24px rgba(99,102,241,0.25) !important;
}
button[id$="-btn"]:active, button[id$="-run-btn"]:active {
    transform: translateY(0);
}

/* ─── Inputs ─── */
input, select {
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
input:focus, select:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-glow) !important;
    outline: none !important;
}

/* ─── Tables ─── */
table {
    border-spacing: 0;
}
table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
}
table tbody tr {
    transition: background 0.15s;
}
table tbody tr:hover {
    background: rgba(99,102,241,0.04) !important;
}

/* ─── Scrollbar ─── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background: rgba(99,102,241,0.2);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(99,102,241,0.35);
}

/* ─── Animations ─── */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
@keyframes progress {
    0% { width: 0%; }
    50% { width: 100%; }
    100% { width: 0%; }
}
@keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes gradientShift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* ─── Strategy cards ─── */
[id="page-strategies"] > div > div > div {
    transition: transform 0.25s cubic-bezier(.4,0,.2,1), box-shadow 0.25s;
}
[id="page-strategies"] > div > div > div:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(99,102,241,0.15) !important;
}

/* ─── Toast ─── */
[id="toast-container"] > div {
    animation: toastSlideIn 0.4s cubic-bezier(.4,0,.2,1);
}
@keyframes toastSlideIn {
    from { opacity: 0; transform: translateX(40px); }
    to   { opacity: 1; transform: translateX(0); }
}

/* ─── Background subtle noise ─── */
body::before {
    content: '';
    position: fixed;
    inset: 0;
    z-index: -1;
    opacity: 0.015;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
    pointer-events: none;
}
</style>
<script>
document.addEventListener('DOMContentLoaded', function() {
    var pageMap = {
        'nav-overview': 'overview', 'nav-backtest': 'backtest',
        'nav-strategies': 'strategies', 'nav-trading': 'trading',
        'nav-ai': 'ai', 'nav-data': 'data',
        'nav-logs': 'logs', 'nav-settings': 'settings'
    };
    var titleMap = {
        'overview': '总览', 'backtest': '回测', 'strategies': '策略',
        'trading': '交易', 'ai': 'AI分析', 'data': '数据',
        'logs': '日志', 'settings': '设置'
    };
    var allPages = ['overview','backtest','strategies','trading','ai','data','logs','settings'];

    function switchPage(pageId) {
        allPages.forEach(function(pid) {
            var el = document.getElementById('page-' + pid);
            if (el) {
                if (pid === pageId) {
                    el.style.display = 'block';
                    el.style.animation = 'none';
                    el.offsetHeight;
                    el.style.animation = 'pageFadeIn 0.35s cubic-bezier(.4,0,.2,1)';
                } else {
                    el.style.display = 'none';
                }
            }
        });
        allPages.forEach(function(pid) {
            var btn = document.getElementById('nav-' + pid);
            if (btn) {
                if (pid === pageId) {
                    btn.className = 'nav-btn active';
                } else {
                    btn.className = 'nav-btn';
                }
            }
        });
        var titleEl = document.getElementById('page-title');
        if (titleEl) titleEl.textContent = titleMap[pageId] || pageId;
        var storeEl = document.getElementById('current-page');
        if (storeEl) {
            var ev = new CustomEvent('_dashclient_store_updated', {bubbles: true});
            storeEl.setAttribute('data-dash-is-loading', '');
        }
        history.pushState(null, '', '/' + pageId);
    }

    function handleClick(e) {
        var btn = e.target.closest('[id^="nav-"]');
        if (!btn) return;
        var pageId = pageMap[btn.id];
        if (pageId) {
            e.preventDefault();
            e.stopPropagation();
            switchPage(pageId);
        }
    }

    document.addEventListener('click', handleClick, true);

    window.addEventListener('popstate', function(e) {
        var path = window.location.pathname.replace(/^\\//, '') || 'overview';
        if (allPages.indexOf(path) !== -1) {
            switchPage(path);
        }
    });
});
</script>
</head>
<body>
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>"""

    app.layout = html.Div([
        dcc.Location(id="url", refresh=False),
        _sidebar(),

        html.Div([
            _header(),

            html.Div([
                html.Div(_page_overview(), id="page-overview", style={"display": "block"}),
                html.Div(_page_backtest(), id="page-backtest", style={"display": "none"}),
                html.Div(_page_strategies(), id="page-strategies", style={"display": "none"}),
                html.Div(_page_trading(), id="page-trading", style={"display": "none"}),
                html.Div(_page_ai(), id="page-ai", style={"display": "none"}),
                html.Div(_page_data(), id="page-data", style={"display": "none"}),
                html.Div(_page_logs(), id="page-logs", style={"display": "none"}),
                html.Div(_page_settings(), id="page-settings", style={"display": "none"}),
            ], style={
                "padding": "24px 32px",
                "overflowY": "auto",
                "height": "calc(100vh - 120px)",
            }),
        ], style={
            "marginLeft": f"{SIDEBAR_WIDTH}px",
            "display": "flex", "flexDirection": "column",
            "height": "100vh",
        }),

        dcc.Interval(id="global-timer", interval=5000),
        dcc.Store(id="current-page", data="overview"),
        dcc.Store(id="backtest-result-store"),
        dcc.Store(id="api-keys-store", data={
            "deepseek_key": "",
            "openai_key": "",
            "anthropic_key": "",
        }),
        dcc.Store(id="market-data-store", data={
            "prices": {},
            "timestamp": None,
            "source": "pending",
        }),
        dcc.Interval(id="market-refresh", interval=5000),
        html.Div(id="toast-container"),
    ], style={
        "backgroundColor": COLORS["bg_base"],
        "minHeight": "100vh",
        "fontFamily": FONT_UI,
        "color": COLORS["text_primary"],
    })

    _register_callbacks(app)

    return app


def _register_callbacks(app: dash.Dash):

    page_ids = [item['id'] for item in NAV_ITEMS]
    nav_ids = [f"nav-{item['id']}" for item in NAV_ITEMS]
    title_map = {item['id']: item['label'] for item in NAV_ITEMS}
    nav_id_to_page = {f"nav-{item['id']}": item['id'] for item in NAV_ITEMS}

    @app.callback(
        Output("live-clock", "children"),
        Input("global-timer", "n_intervals"),
    )
    def update_clock(_):
        return datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    @app.callback(
        [Output("bt-results", "children"),
         Output("bt-results", "style"),
         Output("bt-status", "children"),
         Output("backtest-result-store", "data")],
        Input("bt-run-btn", "n_clicks"),
        [State("bt-strategy", "value"),
         State("bt-symbol", "value"),
         State("bt-timeframe", "value"),
         State("bt-capital", "value"),
         State("bt-market", "value")],
        prevent_initial_call=True,
    )
    def run_backtest(n_clicks, strategy, symbol, timeframe, capital, market):
        if not n_clicks:
            return "", {"display": "none"}, "", None

        import asyncio
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

        from quantengine.backtest.engine import BacktestEngine
        from quantengine.strategy.builtin.dual_thrust import DualThrustStrategy
        from quantengine.strategy.builtin.turtle import TurtleStrategy
        from quantengine.strategy.builtin.bollinger import BollingerStrategy
        from quantengine.strategy.builtin.dual_ma import DualMAStrategy
        from quantengine.strategy.builtin.r_breaker import RBreakerStrategy
        from quantengine.strategy.builtin.grid_ma import GridMAStrategy
        from quantengine.strategy.builtin.simple_mm import SimpleMarketMaker
        from quantengine.strategy.builtin.panic_reversal import PanicReversalStrategy
        from quantengine.strategy.builtin.low_vol_defense import LowVolDefenseStrategy
        from quantengine.strategy.builtin.aberration import AberrationStrategy
        from quantengine.strategy.builtin.rsi_reversal import RSIReversalStrategy
        from quantengine.strategy.builtin.pivot_point import PivotPointStrategy
        from quantengine.strategy.builtin.fei_ali import FeiAliStrategy
        from quantengine.strategy.builtin.dynamic_breakout_ii import DynamicBreakoutIIStrategy
        from quantengine.strategy.builtin.multi_factor import MultiFactorStrategy
        from quantengine.strategy.builtin.sector_rotation import SectorRotationStrategy

        STRATEGY_CLASSES = {
            "dual_thrust": (DualThrustStrategy, {"k1": 0.7, "k2": 0.7}),
            "turtle": (TurtleStrategy, {"entry_period": 20}),
            "bollinger": (BollingerStrategy, {"period": 20}),
            "dual_ma": (DualMAStrategy, {"fast_period": 5, "slow_period": 20}),
            "r_breaker": (RBreakerStrategy, {}),
            "grid_ma": (GridMAStrategy, {"ma_period": 20}),
            "simple_mm": (SimpleMarketMaker, {}),
            "panic_reversal": (PanicReversalStrategy, {}),
            "low_vol_defense": (LowVolDefenseStrategy, {}),
            "aberration": (AberrationStrategy, {"period": 20, "num_std": 2.0}),
            "rsi_reversal": (RSIReversalStrategy, {"rsi_period": 14}),
            "pivot_point": (PivotPointStrategy, {"sensitivity": "moderate"}),
            "fei_ali": (FeiAliStrategy, {"atr_mult_sl": 1.5, "atr_mult_tp": 3.0}),
            "dynamic_breakout_ii": (DynamicBreakoutIIStrategy, {"base_period": 20}),
            "multi_factor": (MultiFactorStrategy, {"factors": ["momentum", "volatility", "rsi"]}),
            "sector_rotation": (SectorRotationStrategy, {"rotation_period": 20}),
        }

        if strategy not in STRATEGY_CLASSES:
            return (
                html.Div(f"⚠️ 策略 {strategy} 需要联网数据，请在本地使用 CLI 回测"),
                {"display": "block", "marginTop": "16px"},
                html.Span("⚠️ 不支持在线回测", style={"color": COLORS["warning"]}),
                None,
            )

        try:
            status = html.Div([
                html.Span("⟳", style={"animation": "spin 1s linear infinite"}),
                "正在生成模拟数据...",
            ], style={"display": "flex", "alignItems": "center", "gap": "8px"})

            import numpy as np
            np.random.seed(42)
            n = 500
            prices = 100 + np.random.randn(n).cumsum() * 2
            df = pd.DataFrame({
                "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
                "open": prices - np.random.rand(n) * 0.5,
                "high": prices + np.random.rand(n) * 1,
                "low": prices - np.random.rand(n) * 1,
                "close": prices + np.random.randn(n) * 0.3,
                "volume": np.random.randint(100, 10000, n),
            })

            engine = BacktestEngine(initial_capital=float(capital), market=market)
            cls, params = STRATEGY_CLASSES[strategy]
            engine.add_strategy(cls(params), symbols=[symbol], weight=1.0, timeframe=timeframe)
            report = engine.run({symbol: df})

            eq = engine.equity_curve
            report["equity_curve"] = list(zip(
                eq["timestamp"].astype(str).tolist(),
                eq["equity"].tolist()
            )) if not eq.empty else []
            report["trades"] = [
                {
                    "symbol": t.get("symbol", symbol),
                    "side": t.get("side", "BUY"),
                    "quantity": t.get("quantity", 0),
                    "entry_price": t.get("entry_price", 0),
                    "exit_price": t.get("exit_price", 0),
                    "pnl": t.get("pnl", 0),
                }
                for t in engine.trades.to_dict("records")
            ] if not engine.trades.empty else []
            report["initial_capital"] = float(capital)

            results_html = _build_backtest_results(report)
            status = html.Span(f"✅ 完成 ({report.get('trading_days', 0)} bars)",
                               style={"color": COLORS["success"]})

            return results_html, {"display": "block", "marginTop": "16px"}, status, json.dumps(report, default=str)

        except Exception as e:
            import traceback
            return (
                html.Div([
                    html.Div("❌ 回测异常", style={
                        "fontSize": "16px", "fontWeight": "600",
                        "color": COLORS["danger"], "marginBottom": "8px",
                    }),
                    html.Div(str(e), style={"color": COLORS["text_secondary"],
                              "fontSize": "13px", "whiteSpace": "pre-wrap"}),
                ]),
                {"display": "block", "marginTop": "16px"},
                html.Span("❌ 失败", style={"color": COLORS["danger"]}),
                None,
            )

    @app.callback(
        Output("dl-status", "children"),
        Input("dl-run-btn", "n_clicks"),
        [State("dl-market", "value"),
         State("dl-symbols", "value"),
         State("dl-freq", "value"),
         State("dl-limit", "value")],
        prevent_initial_call=True,
    )
    def download_data(n_clicks, market, symbols, freq, limit):
        if not n_clicks:
            return ""

        import asyncio

        try:
            sym_list = [s.strip() for s in (symbols or "BTC/USDT").split(",")]
            result_parts = []

            if market == "crypto":
                from quantengine.data.ccxt_fetcher import CCXTQuoteFetcher
                fetcher = CCXTQuoteFetcher({"exchange": "binance"})
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for sym in sym_list:
                    df = loop.run_until_complete(
                        fetcher.fetch_kline(symbol=sym, freq=freq or "1h", limit=int(limit or 100))
                    )
                    if not df.empty:
                        count = len(df)
                        result_parts.append(f"{sym}: {count} bar")
                    else:
                        result_parts.append(f"{sym}: 无数据")
                loop.close()
            elif market == "a_share":
                from quantengine.data.akshare_fetcher import AkshareQuoteFetcher
                fetcher = AkshareQuoteFetcher({})
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                for sym in sym_list:
                    df = loop.run_until_complete(
                        fetcher.fetch_kline(symbol=sym, freq=freq or "1d", limit=int(limit or 100))
                    )
                    if not df.empty:
                        result_parts.append(f"{sym}: {len(df)} bar")
                    else:
                        result_parts.append(f"{sym}: 无数据")
                loop.close()
            else:
                return html.Span(f"未知市场: {market}", style={"color": COLORS["danger"]})

            return html.Div([
                html.Div("✅ 数据下载完成", style={"color": COLORS["success"], "fontWeight": "600"}),
                html.Div(" | ".join(result_parts), style={
                    "color": COLORS["text_secondary"], "fontSize": "13px", "marginTop": "4px"}),
            ])

        except Exception as e:
            return html.Div([
                html.Div("❌ 下载失败", style={"color": COLORS["danger"], "fontWeight": "600"}),
                html.Div(str(e), style={"color": COLORS["text_muted"], "fontSize": "12px", "marginTop": "4px"}),
            ])

    @app.callback(
        Output("market-data-store", "data"),
        Input("market-refresh", "n_intervals"),
        prevent_initial_call=False,
    )
    def refresh_market_data(n_intervals):
        import concurrent.futures
        import random

        prices = {"crypto": {}, "a_share": {}, "us_stock": {}}
        changes = {}
        source_parts = []
        now = datetime.now().isoformat()

        def _fetch_crypto():
            try:
                import asyncio
                from quantengine.data.ccxt_fetcher import CCXTQuoteFetcher
                fetcher = CCXTQuoteFetcher({"exchange": "binance"})
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                btc = loop.run_until_complete(fetcher.fetch_realtime_quote("BTC/USDT"))
                eth = loop.run_until_complete(fetcher.fetch_realtime_quote("ETH/USDT"))
                loop.close()
                return {
                    "BTC/USDT": {"price": btc.get("price", 0), "change_pct": btc.get("change_pct", 0)},
                    "ETH/USDT": {"price": eth.get("price", 0), "change_pct": eth.get("change_pct", 0)},
                }, "币安"
            except Exception:
                return None, None

        def _fetch_ashare():
            try:
                import akshare as ak
                df = ak.stock_zh_a_spot_em()
                if df is None or df.empty:
                    return None, None

                index_codes = {
                    "000001": "上证指数", "399001": "深证成指",
                    "000300": "沪深300", "000688": "科创50",
                }
                hot_stocks = {"600519": "贵州茅台", "300750": "宁德时代",
                              "000858": "五粮液", "601318": "中国平安"}
                result = {}
                for code, name in {**index_codes, **hot_stocks}.items():
                    row = df[df["代码"] == code]
                    if not row.empty:
                        result[name] = {
                            "price": float(row.iloc[0].get("最新价", 0) or 0),
                            "change_pct": float(row.iloc[0].get("涨跌幅", 0) or 0),
                        }
                return result, "东方财富"
            except Exception:
                return None, None

        def _fetch_us():
            try:
                import akshare as ak
                df = ak.stock_us_famous_spot_em()
                if df is None or df.empty:
                    return None, None

                us_map = {
                    ".IXIC": "纳斯达克", ".INX": "标普500",
                    "AAPL": "苹果", "TSLA": "特斯拉",
                    "MSFT": "微软", "AMZN": "亚马逊",
                }
                result = {}
                for code, name in us_map.items():
                    row = df[df["代码"] == code] if "代码" in df.columns else df[df.iloc[:, 0].astype(str).str.contains(code)]
                    if not row.empty:
                        r = row.iloc[0]
                        result[name] = {
                            "price": float(r.get("最新价", r.get("实时价格", 0)) or 0),
                            "change_pct": float(r.get("涨跌幅", r.get("涨幅", 0)) or 0),
                        }
                if not result.get("标普500") or not result.get("纳斯达克"):
                    try:
                        gdf = ak.index_global_spot_em()
                        gmap = {"S&P 500": "标普500", "NASDAQ": "纳斯达克"}
                        for gname, alias in gmap.items():
                            row = gdf[gdf["名称"].str.contains(gname, na=False)] if "名称" in gdf.columns else None
                            if row is not None and not row.empty:
                                r = row.iloc[0]
                                result[alias] = {
                                    "price": float(r.get("最新价", 0) or 0),
                                    "change_pct": float(r.get("涨跌幅", 0) or 0),
                                }
                    except Exception:
                        pass
                return result, "东方财富"
            except Exception:
                return None, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futs = {
                "crypto": executor.submit(_fetch_crypto),
                "a_share": executor.submit(_fetch_ashare),
                "us_stock": executor.submit(_fetch_us),
            }
            crypto_result, crypto_src = futs["crypto"].result() or (None, None)
            ashare_result, ashare_src = futs["a_share"].result() or (None, None)
            us_result, us_src = futs["us_stock"].result() or (None, None)

        if crypto_result:
            prices["crypto"] = crypto_result
            source_parts.append(crypto_src or "币安")
        else:
            base_btc = 67500
            prices["crypto"] = {
                "BTC/USDT": {"price": round(base_btc + random.uniform(-200, 200), 2),
                             "change_pct": round(random.uniform(-2, 2), 2)},
                "ETH/USDT": {"price": round(3450 + random.uniform(-30, 30), 2),
                             "change_pct": round(random.uniform(-2, 2), 2)},
            }
            source_parts.append("模拟")

        if ashare_result:
            prices["a_share"] = ashare_result
            source_parts.append(ashare_src or "东方财富")
        else:
            prices["a_share"] = {
                "上证指数": {"price": round(3150 + random.uniform(-10, 10), 2),
                           "change_pct": round(random.uniform(-1, 1), 2)},
                "沪深300": {"price": round(3780 + random.uniform(-10, 10), 2),
                          "change_pct": round(random.uniform(-1, 1), 2)},
                "贵州茅台": {"price": round(1680 + random.uniform(-10, 10), 2),
                          "change_pct": round(random.uniform(-1, 1), 2)},
            }
            source_parts.append("模拟")

        if us_result:
            prices["us_stock"] = us_result
            source_parts.append(us_src or "东方财富")
        else:
            prices["us_stock"] = {
                "标普500": {"price": round(5340 + random.uniform(-20, 20), 2),
                          "change_pct": round(random.uniform(-1, 1), 2)},
                "纳斯达克": {"price": round(16800 + random.uniform(-50, 50), 2),
                           "change_pct": round(random.uniform(-1, 1), 2)},
                "苹果": {"price": round(192 + random.uniform(-2, 2), 2),
                        "change_pct": round(random.uniform(-1.5, 1.5), 2)},
            }
            source_parts.append("模拟")

        return {
            "prices": prices,
            "timestamp": now,
            "source": "+".join(set(source_parts)),
        }

    def _save_key_to_env(key_name: str, key_value: str) -> None:
        """将 API Key 安全写入 .env 文件。"""
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        # 确保 .env 在 .gitignore 中
        gitignore = env_path.parent / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            if ".env" not in content:
                gitignore.write_text(content + "\n.env\n", encoding="utf-8")
        # 写入 .env
        content = ""
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            lines = [l for l in content.split("\n") if not l.startswith(f"{key_name}=")]
            content = "\n".join(lines)
        content += f"\n{key_name}={key_value}\n"
        env_path.write_text(content.strip() + "\n", encoding="utf-8")
        # Unix/Linux: 设置文件权限为 600（仅所有者可读写）
        import os
        import sys as _sys
        if _sys.platform != "win32":
            try:
                os.chmod(env_path, 0o600)
            except OSError:
                pass

    def _try_keyring_store(service: str, key: str) -> bool:
        """尝试使用系统密钥管理器存储（keyring）。返回是否成功。"""
        try:
            import keyring
            keyring.set_password("QuantEnginePro", service, key)
            return True
        except Exception:
            return False

    @app.callback(
        [Output("deepseek-key-status", "children"),
         Output("api-keys-store", "data")],
        Input("save-deepseek-key", "n_clicks"),
        State("cfg-deepseek-key", "value"),
        State("api-keys-store", "data"),
        prevent_initial_call=True,
    )
    def save_deepseek_key(n, key, store):
        if not key or not key.startswith("sk-"):
            return html.Span("⚠️ 请输入有效的 API Key（以 sk- 开头）",
                            style={"color": COLORS["warning"]}), store
        store = dict(store)  # 不可变副本
        store["deepseek_key"] = key
        storage_methods = []
        # 1. 尝试 keyring（最安全）
        if _try_keyring_store("deepseek", key):
            storage_methods.append("系统密钥链")
        # 2. 尝试 .env（明文但持久）
        try:
            _save_key_to_env("DEEPSEEK_API_KEY", key)
            storage_methods.append(".env（明文）")
        except Exception:
            pass
        method_str = " + ".join(storage_methods) if storage_methods else "内存（仅本次会话）"
        return html.Span([
            html.Span("✅ 已保存", style={"color": COLORS["success"]}),
            html.Span(f" 存储: {method_str}",
                     style={"color": COLORS["text_muted"], "fontSize": "11px", "marginLeft": "8px"}),
        ]), store

    @app.callback(
        [Output("openai-key-status", "children"),
         Output("api-keys-store", "data")],
        Input("save-openai-key", "n_clicks"),
        State("cfg-openai-key", "value"),
        State("api-keys-store", "data"),
        prevent_initial_call=True,
    )
    def save_openai_key(n, key, store):
        if not key or not key.startswith("sk-"):
            return html.Span("⚠️ 请输入有效的 API Key（以 sk- 开头）",
                            style={"color": COLORS["warning"]}), store
        store = dict(store)
        store["openai_key"] = key
        storage_methods = []
        if _try_keyring_store("openai", key):
            storage_methods.append("系统密钥链")
        try:
            _save_key_to_env("OPENAI_API_KEY", key)
            storage_methods.append(".env（明文）")
        except Exception:
            pass
        method_str = " + ".join(storage_methods) if storage_methods else "内存（仅本次会话）"
        return html.Span([
            html.Span("✅ 已保存", style={"color": COLORS["success"]}),
            html.Span(f" 存储: {method_str}",
                     style={"color": COLORS["text_muted"], "fontSize": "11px", "marginLeft": "8px"}),
        ]), store

    @app.callback(
        [Output("anthropic-key-status", "children"),
         Output("api-keys-store", "data")],
        Input("save-anthropic-key", "n_clicks"),
        State("cfg-anthropic-key", "value"),
        State("api-keys-store", "data"),
        prevent_initial_call=True,
    )
    def save_anthropic_key(n, key, store):
        if not key or not key.startswith("sk-ant-"):
            return html.Span("⚠️ 请输入有效的 API Key（以 sk-ant- 开头）",
                            style={"color": COLORS["warning"]}), store
        store = dict(store)
        store["anthropic_key"] = key
        storage_methods = []
        if _try_keyring_store("anthropic", key):
            storage_methods.append("系统密钥链")
        try:
            _save_key_to_env("ANTHROPIC_API_KEY", key)
            storage_methods.append(".env（明文）")
        except Exception:
            pass
        method_str = " + ".join(storage_methods) if storage_methods else "内存（仅本次会话）"
        return html.Span([
            html.Span("✅ 已保存", style={"color": COLORS["success"]}),
            html.Span(f" 存储: {method_str}",
                     style={"color": COLORS["text_muted"], "fontSize": "11px", "marginLeft": "8px"}),
        ]), store

    @app.callback(
        Output("ticker-bar", "children"),
        Input("market-data-store", "data"),
    )
    def update_ticker_bar(data):
        if not data or not data.get("prices"):
            return "等待行情数据..."

        prices = data["prices"]

        def _tile(market_key, label, items):
            parts = []
            for sym in items:
                item = prices.get(market_key, {}).get(sym)
                if not item:
                    parts.append(html.Span(f"{sym} ...", style={"color": COLORS["text_muted"]}))
                    continue
                p = item.get("price", 0) or 0
                chg = item.get("change_pct", 0) or 0
                color = COLORS["profit"] if chg > 0 else COLORS["loss"] if chg < 0 else COLORS["text_primary"]
                parts.append(html.Span([
                    html.Span(f"{sym} ", style={"color": COLORS["text_secondary"], "fontSize": "12px"}),
                    html.Span(f"{p:,.2f}" if p < 100 else f"${p:,.0f}" if market_key == "crypto" else f"{p:,.2f}",
                             style={"fontWeight": "700", "fontSize": "14px", "color": COLORS["text_primary"], "fontFamily": FONT_MONO}),
                    html.Span(f"  {chg:+.2f}%", style={"fontSize": "12px", "fontWeight": "500", "color": color}),
                ], style={"display": "inline-flex", "alignItems": "center", "gap": "3px", "marginRight": "14px"}))
            return html.Div([
                html.Span(label, style={"fontSize": "11px", "fontWeight": "600",
                           "color": COLORS["text_muted"], "marginRight": "6px"}),
                *parts,
            ], style={"display": "flex", "alignItems": "center", "flex": "1"})

        return html.Div([
            _tile("crypto", "💎", ["BTC/USDT", "ETH/USDT"]),
            html.Div(style={"width": "1px", "height": "30px", "background": COLORS["border"]}),
            _tile("a_share", "🇨🇳", ["上证指数", "沪深300", "贵州茅台"]),
            html.Div(style={"width": "1px", "height": "30px", "background": COLORS["border"]}),
            _tile("us_stock", "🇺🇸", ["标普500", "纳斯达克", "苹果"]),
        ], style={"display": "flex", "alignItems": "center", "width": "100%", "gap": "8px"})

    @app.callback(
        [Output("ai-status", "children"),
         Output("ai-sentiment-chart", "figure"),
         Output("ai-news-list", "children"),
         Output("ai-picks", "children"),
         Output("ai-signals", "children")],
        Input("ai-fetch-btn", "n_clicks"),
        [State("market-data-store", "data"),
         State("api-keys-store", "data")],
        prevent_initial_call=True,
    )
    def run_ai_analysis(n_clicks, mkt_data, api_keys):
        import asyncio
        api_key = api_keys.get("deepseek_key", "")
        if not api_key:
            return (
                html.Span("⚠️ 请先在「设置」页面配置 DeepSeek API Key",
                         style={"color": COLORS["warning"]}),
                _empty_chart("请配置 API Key"), html.Div(), html.Div(), html.Div(),
            )
        try:
            try:
                from quantengine.data.news_fetcher import CailianNewsFetcher
                fetcher = CailianNewsFetcher({})
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                news_items = loop.run_until_complete(
                    fetcher.fetch_news(symbols=None, date=None, limit=8)
                )
                loop.close()
            except Exception:
                news_items = []

            if not news_items:
                class MockNews:
                    def __init__(self, t, c): self.title = t; self.content = c; self.source = "模拟"
                news_items = [
                    MockNews("BTC 突破 68000 美元关口", "比特币价格强势突破关键阻力位，市场情绪积极"),
                    MockNews("市场情绪回暖资金流入", "主流加密货币资金净流入持续增长"),
                    MockNews("监管政策预期明朗", "多家机构提交 ETF 申请，市场信心增强"),
                ]

            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            analyzed = []
            for item in news_items:
                try:
                    resp = client.chat.completions.create(
                        model="deepseek-v4-flash",
                        messages=[{"role": "system",
                                   "content": "返回JSON: {\"sentiment\":\"positive/negative/neutral\",\"score\":0-1,\"summary\":\"摘要\"}"},
                                  {"role": "user", "content": f"标题:{item.title} 内容:{item.content[:300]}"}],
                        max_tokens=200, temperature=0.3,
                    )
                    raw = resp.choices[0].message.content.strip().replace("```json","").replace("```","")
                    result = json.loads(raw)
                except Exception:
                    result = {"sentiment": "neutral", "score": 0.5, "summary": item.title[:50]}
                analyzed.append(result)

            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Scatter(y=[a["score"] if a.get("sentiment")=="positive" else 0.5 for a in analyzed],
                                     mode="markers+lines", name="正面", line=dict(color=COLORS["success"])))
            fig.add_trace(go.Scatter(y=[a["score"] if a.get("sentiment")=="negative" else 0.5 for a in analyzed],
                                     mode="markers+lines", name="负面", line=dict(color=COLORS["danger"])))
            fig.update_layout(title="新闻情感分析", template="plotly_dark",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font={"color": COLORS["text_secondary"], "size": 11},
                              height=300, margin=dict(l=40, r=20, t=40, b=40),
                              xaxis={"gridcolor": "rgba(255,255,255,0.03)"},
                              yaxis={"range": [0, 1], "gridcolor": "rgba(255,255,255,0.03)"},
                              hovermode="x unified")

            news_html = html.Div([
                html.Div([
                    html.Span(f"{'🟢' if a.get('sentiment')=='positive' else '🔴' if a.get('sentiment')=='negative' else '⚪'} "),
                    html.Span(a.get("summary",""), style={"fontSize":"13px"}),
                ], style={"padding":"8px 12px","borderBottom":f"1px solid {COLORS['border']}"})
                for a in analyzed
            ])
            pos = sum(1 for a in analyzed if a.get("sentiment")=="positive")
            picks = html.Div([
                html.Div(f"📊 {len(analyzed)} 条分析, {pos} 条正面", style={"fontSize":"13px"}),
                html.Div("情绪: " + ("🟢 偏积极" if pos>len(analyzed)*0.4 else "⚪ 中性"),
                        style={"fontSize":"13px","color":COLORS["text_muted"]}),
            ])
            signals = html.Div([
                html.Div("信号: " + ("BTC 可关注" if pos>len(analyzed)*0.4 else "建议观望"),
                        style={"fontSize":"13px","color":COLORS["text_secondary"]}),
            ])
            return (
                html.Span(f"✅ 完成 ({len(analyzed)} 条)", style={"color": COLORS["success"]}),
                fig, news_html, picks, signals,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return (
                html.Span(f"❌ 失败: {e}", style={"color": COLORS["danger"]}),
                _empty_chart("分析失败"), html.Div(), html.Div(), html.Div(),
            )

    @app.callback(
        Output("exec-status-text", "children"),
        [Input("exec-start-btn", "n_clicks"), Input("exec-stop-btn", "n_clicks")],
        prevent_initial_call=True,
    )
    def toggle_executor(start_clicks, stop_clicks):
        ctx = callback_context
        if not ctx.triggered:
            return "执行器未运行"
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "exec-start-btn":
            if _live_executor_ref:
                try:
                    _live_executor_ref.start()
                    return "✅ 执行器已启动"
                except Exception as e:
                    return f"❌ 启动失败: {e}"
            return "⚠️ 执行器未配置，请先在设置页面配置券商连接"
        elif trigger == "exec-stop-btn":
            if _live_executor_ref:
                try:
                    _live_executor_ref.stop()
                    return "⏹ 执行器已停止"
                except Exception as e:
                    return f"❌ 停止失败: {e}"
            return "执行器未运行"
        return "执行器未运行"

    @app.callback(
        Output("toast-container", "children"),
        Input("backtest-result-store", "data"),
        prevent_initial_call=True,
    )
    def show_toast(data):
        if data:
            return html.Div("✅ 回测完成", style={
                "position": "fixed", "bottom": "24px", "right": "24px",
                "background": f"linear-gradient(135deg, {COLORS['gradient_start']}, {COLORS['gradient_end']})",
                "color": "white",
                "padding": "12px 24px", "borderRadius": "10px",
                "fontSize": "14px", "fontWeight": "500", "zIndex": "1000",
                "boxShadow": f"0 4px 16px {COLORS['accent_glow']}",
                "fontFamily": FONT_UI,
            })
        return ""
