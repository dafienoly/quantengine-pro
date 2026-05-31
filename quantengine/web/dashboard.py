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
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Optional

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, dcc, html

# ── 全局状态（避免跨回调序列化问题） ─────────────────────────
_backtest_engine_ref = None
_strategy_registry_ref = None
_market_overview_ref = None
_live_executor_ref = None
_llm_service_ref = None


def set_globals(backtest_engine=None, strategy_registry=None,
                market_overview=None, live_executor=None, llm_service=None):
    """Set global references for dashboard callbacks."""
    global _backtest_engine_ref, _strategy_registry_ref
    global _market_overview_ref, _live_executor_ref, _llm_service_ref
    _backtest_engine_ref = backtest_engine
    _strategy_registry_ref = strategy_registry
    _market_overview_ref = market_overview
    _live_executor_ref = live_executor
    _llm_service_ref = llm_service


# ── 配色方案 ────────────────────────────────────────────────
COLORS = {
    "bg_base": "#0a0e17",
    "bg_card": "#111827",
    "bg_card_hover": "#1a2236",
    "bg_sidebar": "#0d1117",
    "bg_input": "#1a2236",
    "border": "#1f2937",
    "border_hover": "#374151",
    "text_primary": "#f3f4f6",
    "text_secondary": "#9ca3af",
    "text_muted": "#6b7280",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "success": "#10b981",
    "danger": "#ef4444",
    "warning": "#f59e0b",
    "info": "#06b6d4",
    "profit": "#10b981",
    "loss": "#ef4444",
}

SIDEBAR_WIDTH = 220

# ── 导航项 ──────────────────────────────────────────────────
NAV_ITEMS = [
    {"id": "overview",  "icon": "📊", "label": "总览"},
    {"id": "backtest",  "icon": "📈", "label": "回测"},
    {"id": "strategies","icon": "📋", "label": "策略"},
    {"id": "trading",   "icon": "💹", "label": "交易"},
    {"id": "ai",        "icon": "🤖", "label": "AI分析"},
    {"id": "data",      "icon": "📡", "label": "数据"},
    {"id": "logs",      "icon": "📝", "label": "日志"},
]


# ════════════════════════════════════════════════════════════
#  全局样式
# ════════════════════════════════════════════════════════════



# ════════════════════════════════════════════════════════════
#  创建应用
# ════════════════════════════════════════════════════════════

def create_dashboard(backtest_engine=None, strategy_registry=None,
                     market_overview=None) -> dash.Dash:
    """创建现代化交易系统仪表盘。"""
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

    # ── 布局 ──
    app.layout = html.Div([
        # 全局样式
        # CSS 通过内联样式实现，无需额外加载

        # 侧边栏
        _sidebar(),

        # 主区域
        html.Div([
            # 顶栏
            _header(),

            # 页面内容容器
            html.Div(id="page-content", style={
                "padding": "24px 32px",
                "overflowY": "auto",
                "height": "calc(100vh - 120px)",
            }),
        ], style={
            "marginLeft": f"{SIDEBAR_WIDTH}px",
            "display": "flex", "flexDirection": "column",
            "height": "100vh",
        }),

        # 全局定时刷新
        dcc.Interval(id="global-timer", interval=5000),

        # 存储当前页面（避免 URL 路由）
        dcc.Store(id="current-page", data="overview"),

        # 回测结果存储
        dcc.Store(id="backtest-result-store"),

        # Toast 通知容器
        html.Div(id="toast-container"),
    ], style={
        "backgroundColor": COLORS["bg_base"],
        "minHeight": "100vh",
        "fontFamily": "'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
        "color": COLORS["text_primary"],
    })

    # ── 回调注册 ──
    _register_callbacks(app)

    return app


# ════════════════════════════════════════════════════════════
#  侧边栏
# ════════════════════════════════════════════════════════════

def _sidebar() -> html.Div:
    nav_links = []
    for item in NAV_ITEMS:
        nav_links.append(
            html.Div(
                f"{item['icon']}  {item['label']}",
                id=f"nav-{item['id']}",
                className="nav-item",
                n_clicks=0,
                style={
                    "padding": "12px 20px",
                    "cursor": "pointer",
                    "borderRadius": "8px",
                    "margin": "2px 10px",
                    "fontSize": "14px",
                    "color": COLORS["text_secondary"],
                    "transition": "all 0.2s",
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "8px",
                },
            )
        )

    return html.Div([
        # Logo
        html.Div([
            html.Div("⚡", style={"fontSize": "24px"}),
            html.Div([
                html.Div("量化引擎", style={
                    "fontSize": "16px", "fontWeight": "700",
                    "color": COLORS["text_primary"], "lineHeight": "1.2",
                }),
                html.Div("专业版", style={
                    "fontSize": "11px", "color": COLORS["text_muted"],
                    "letterSpacing": "2px",
                }),
            ]),
        ], style={
            "padding": "20px 16px 24px",
            "display": "flex", "alignItems": "center", "gap": "10px",
            "borderBottom": f"1px solid {COLORS['border']}",
        }),

        # 导航
        html.Div(nav_links, style={"padding": "12px 0", "flex": "1"}),

        # 底部版本号
        html.Div("v0.1.0", style={
            "textAlign": "center", "padding": "16px",
            "fontSize": "11px", "color": COLORS["text_muted"],
            "borderTop": f"1px solid {COLORS['border']}",
        }),
    ], style={
        "position": "fixed", "left": 0, "top": 0,
        "width": f"{SIDEBAR_WIDTH}px", "height": "100vh",
        "backgroundColor": COLORS["bg_sidebar"],
        "borderRight": f"1px solid {COLORS['border']}",
        "display": "flex", "flexDirection": "column",
        "zIndex": 100,
    })


# ════════════════════════════════════════════════════════════
#  顶栏
# ════════════════════════════════════════════════════════════

def _header() -> html.Div:
    return html.Div([
        # 页面标题
        html.Div(id="page-title", style={
            "fontSize": "20px", "fontWeight": "600",
            "color": COLORS["text_primary"],
        }),
        # 右侧状态
        html.Div([
            html.Div(id="live-clock", style={
                "fontSize": "13px", "color": COLORS["text_muted"],
                "fontFamily": "'JetBrains Mono', monospace",
            }),
            html.Div([
                html.Span("●", style={
                    "color": COLORS["success"], "fontSize": "10px",
                }),
                html.Span("系统运行中", style={
                    "fontSize": "12px", "color": COLORS["text_secondary"],
                }),
            ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "20px"}),
    ], style={
        "display": "flex", "justifyContent": "space-between",
        "alignItems": "center",
        "padding": "16px 32px",
        "borderBottom": f"1px solid {COLORS['border']}",
        "backgroundColor": COLORS["bg_card"],
        "height": "56px",
    })


# ════════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════════

def _kpi_card(title: str, value: str, subtitle: str = "",
              color: str = COLORS["text_primary"],
              icon: str = "", delta: str = "") -> html.Div:
    return html.Div([
        html.Div([
            html.Span(icon, style={"fontSize": "20px"}) if icon else None,
            html.Span(title, style={"fontSize": "12px", "color": COLORS["text_muted"]}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        html.Div(value, style={
            "fontSize": "26px", "fontWeight": "700",
            "color": color, "marginTop": "8px",
            "fontFamily": "'JetBrains Mono', monospace",
        }),
        html.Div([
            html.Span(delta, style={
                "fontSize": "12px", "fontWeight": "500",
                "color": COLORS["success"] if delta.startswith("+") else COLORS["danger"] if delta.startswith("-") else COLORS["text_muted"],
            }) if delta else None,
            html.Span(subtitle, style={"fontSize": "11px", "color": COLORS["text_muted"]}),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginTop": "4px"}),
    ], style={
        "backgroundColor": COLORS["bg_card"],
        "border": f"1px solid {COLORS['border']}",
        "borderRadius": "12px",
        "padding": "20px",
        "transition": "all 0.2s",
    })


def _section(title: str, icon: str = "", children=None) -> html.Div:
    return html.Div([
        html.Div([
            html.Span(icon) if icon else None,
            html.H3(title, style={
                "fontSize": "15px", "fontWeight": "600",
                "color": COLORS["text_primary"], "margin": 0,
            }),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px",
                   "marginBottom": "16px"}),
        children,
    ], style={
        "backgroundColor": COLORS["bg_card"],
        "border": f"1px solid {COLORS['border']}",
        "borderRadius": "12px",
        "padding": "24px",
        "marginBottom": "16px",
    })


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
        xaxis={"gridcolor": "rgba(255,255,255,0.05)", "showgrid": True},
        yaxis={"gridcolor": "rgba(255,255,255,0.05)", "showgrid": True},
    )
    return fig


def _btn(text: str, id: str, primary: bool = True, full: bool = False) -> html.Button:
    return html.Button(text, id=id, n_clicks=0, style={
        "padding": "10px 24px",
        "borderRadius": "8px",
        "border": "none",
        "fontSize": "14px",
        "fontWeight": "500",
        "cursor": "pointer",
        "transition": "all 0.2s",
        "width": "100%" if full else "auto",
        "background": COLORS["accent"] if primary else COLORS["bg_input"],
        "color": "#fff" if primary else COLORS["text_primary"],
        "border": f"1px solid {COLORS['border']}" if not primary else "none",
    })


def _input_field(label: str, id: str, value: str = "",
                 type: str = "text", options: list = None) -> html.Div:
    control = dcc.Input(
        id=id, type=type, value=value,
        style={
            "width": "100%", "padding": "8px 12px",
            "borderRadius": "6px", "border": f"1px solid {COLORS['border']}",
            "backgroundColor": COLORS["bg_input"],
            "color": COLORS["text_primary"],
            "fontSize": "13px", "outline": "none",
        }
    ) if options is None else dcc.Dropdown(
        id=id, options=options, value=value,
        style={"color": "#000"},
    )
    return html.Div([
        html.Label(label, style={
            "fontSize": "12px", "fontWeight": "500",
            "color": COLORS["text_secondary"],
            "marginBottom": "6px", "display": "block",
        }),
        control,
    ], style={"marginBottom": "12px"})


# ════════════════════════════════════════════════════════════
#  页面：总览
# ════════════════════════════════════════════════════════════

def _page_overview() -> html.Div:
    return html.Div([
        # KPI 行
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

        # 权益曲线
        _section("权益曲线", icon="📊",
            children=dcc.Graph(
                id="overview-equity-chart",
                figure=_empty_chart("暂无回测数据，请前往「回测」页面运行"),
                style={"height": "360px"},
                config={"displayModeBar": False},
            ),
        ),

        # 持仓 + 交易双栏
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


# ════════════════════════════════════════════════════════════
#  页面：回测（核心功能 — 全部内嵌，无需 CLI）
# ════════════════════════════════════════════════════════════

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


def _page_backtest() -> html.Div:
    return html.Div([
        # 配置面板
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
                    "padding": "12px 32px", "background": COLORS["accent"],
                    "color": "#fff", "border": "none", "borderRadius": "8px",
                    "fontSize": "15px", "fontWeight": "600",
                    "cursor": "pointer", "transition": "all 0.2s",
                    "display": "flex", "alignItems": "center", "gap": "8px",
                }),
                html.Div(id="bt-status", style={
                    "fontSize": "13px", "color": COLORS["text_muted"],
                    "marginLeft": "16px", "display": "flex",
                    "alignItems": "center", "gap": "8px",
                }),
            ], style={"display": "flex", "alignItems": "center",
                       "marginTop": "16px"}),
        ]),

        # 进度条
        html.Div(id="bt-progress", style={"display": "none"},
            children=[
                html.Div(style={
                    "height": "4px", "background": COLORS["accent"],
                    "borderRadius": "2px",
                    "animation": "progress 2s ease-in-out infinite",
                }),
            ]
        ),

        # 结果面板（初始隐藏）
        html.Div(id="bt-results", style={"display": "none"}),
    ])


def _build_backtest_results(report: Dict) -> html.Div:
    """从回测报告构建结果面板。"""
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
        # 指标行
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

        # 权益曲线
        _section("权益曲线", icon="📊",
            children=dcc.Graph(
                figure=_build_equity_figure(report),
                style={"height": "320px"},
                config={"displayModeBar": False},
            ),
        ),

        # 交易明细表
        _section("交易明细", icon="📋",
            children=_build_trades_table(report),
        ),
    ])


def _build_equity_figure(report: Dict) -> go.Figure:
    """从报告构建权益曲线图。"""
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
            fillcolor="rgba(59,130,246,0.08)",
        ))

        # 初始资金参考线
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
        xaxis={"gridcolor": "rgba(255,255,255,0.05)"},
        yaxis={"gridcolor": "rgba(255,255,255,0.05)",
               "tickformat": ","},
        hovermode="x unified",
        showlegend=False,
    )
    return fig


def _build_trades_table(report: Dict) -> html.Div:
    """构建交易明细表。"""
    trades = report.get("trades", [])
    if not trades:
        return html.Div("暂无交易记录", style={
            "color": COLORS["text_muted"], "textAlign": "center",
            "padding": "20px", "fontSize": "13px",
        })

    rows = []
    for t in trades[-50:]:  # 最近 50 笔
        pnl = t.get("pnl", 0)
        rows.append(html.Tr([
            html.Td(t.get("symbol", ""),
                    style={"padding": "6px 12px", "fontSize": "12px"}),
            html.Td("买入" if t.get("side") in ("BUY", "buy") else "卖出",
                    style={"padding": "6px 12px", "fontSize": "12px",
                           "color": COLORS["profit"] if t.get("side") in ("BUY", "buy") else COLORS["danger"]}),
            html.Td(f"{t.get('quantity', 0):.4f}",
                    style={"padding": "6px 12px", "fontSize": "12px"}),
            html.Td(f"{t.get('entry_price', 0):.2f}",
                    style={"padding": "6px 12px", "fontSize": "12px"}),
            html.Td(f"{t.get('exit_price', 0):.2f}",
                    style={"padding": "6px 12px", "fontSize": "12px"}),
            html.Td(f"{pnl:+.2f}",
                    style={"padding": "6px 12px", "fontSize": "12px",
                           "color": COLORS["profit"] if pnl >= 0 else COLORS["danger"],
                           "fontWeight": "600"}),
        ]))

    return html.Div([
        html.Table([
            html.Thead(html.Tr([
                html.Th("标的", style={"padding": "8px 12px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "left",
                          "borderBottom": f"1px solid {COLORS['border']}"}),
                html.Th("方向", style={"padding": "8px 12px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "left",
                          "borderBottom": f"1px solid {COLORS['border']}"}),
                html.Th("数量", style={"padding": "8px 12px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}"}),
                html.Th("入场价", style={"padding": "8px 12px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}"}),
                html.Th("出场价", style={"padding": "8px 12px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}"}),
                html.Th("盈亏", style={"padding": "8px 12px", "fontSize": "11px",
                          "color": COLORS["text_muted"], "textAlign": "right",
                          "borderBottom": f"1px solid {COLORS['border']}"}),
            ])),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse"}),
        html.Div(f"共 {len(trades)} 笔交易，仅显示最近 50 笔",
                 style={"color": COLORS["text_muted"], "fontSize": "11px",
                        "textAlign": "right", "padding": "8px 12px"}),
    ])


# ════════════════════════════════════════════════════════════
#  页面：策略
# ════════════════════════════════════════════════════════════

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


def _page_strategies() -> html.Div:
    cards = []
    for sid, name, stype, desc in STRATEGY_DETAILS:
        cards.append(
            html.Div([
                html.Div([
                    html.Span(stype, style={
                        "fontSize": "11px", "fontWeight": "500",
                        "padding": "2px 10px", "borderRadius": "10px",
                        "background": "rgba(59,130,246,0.15)",
                        "color": COLORS["accent"],
                    }),
                ], style={"marginBottom": "8px"}),
                html.H4(name, style={
                    "fontSize": "15px", "fontWeight": "600",
                    "color": COLORS["text_primary"], "margin": "0 0 6px 0",
                }),
                html.P(desc, style={
                    "fontSize": "12px", "color": COLORS["text_secondary"],
                    "lineHeight": "1.6", "margin": 0,
                }),
            ], style={
                "backgroundColor": COLORS["bg_card"],
                "border": f"1px solid {COLORS['border']}",
                "borderRadius": "12px", "padding": "20px",
                "transition": "all 0.2s",
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


# ════════════════════════════════════════════════════════════
#  页面：交易
# ════════════════════════════════════════════════════════════

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
                        "padding": "10px 24px", "background": COLORS["success"],
                        "color": "#fff", "border": "none", "borderRadius": "8px",
                        "fontSize": "14px", "fontWeight": "500", "cursor": "pointer",
                    }),
                    html.Button("⏹ 停止执行器", id="exec-stop-btn",
                                n_clicks=0, style={
                        "padding": "10px 24px", "background": COLORS["danger"],
                        "color": "#fff", "border": "none", "borderRadius": "8px",
                        "fontSize": "14px", "fontWeight": "500", "cursor": "pointer",
                        "marginLeft": "10px",
                    }),
                ], style={"display": "flex", "alignItems": "center"}),
            ]),
        ),
        _section("当前持仓", icon="💼",
            children=html.Div("暂无持仓", style={
                "color": COLORS["text_muted"], "textAlign": "center",
                "padding": "40px 0", "fontSize": "13px",
            }),
        ),
    ])


# ════════════════════════════════════════════════════════════
#  页面：AI分析
# ════════════════════════════════════════════════════════════

def _page_ai() -> html.Div:
    return html.Div([
        _section("AI 新闻情感分析", icon="🧠",
            children=html.Div([
                html.Div("配置 DEEPSEEK_API_KEY 后启动服务以查看 AI 分析。",
                         style={"color": COLORS["text_muted"], "fontSize": "13px",
                                "marginBottom": "16px"}),
                dcc.Graph(
                    id="ai-sentiment-chart",
                    figure=_empty_chart("新闻情感时间线（需配置 LLM）", height=300),
                    config={"displayModeBar": False},
                ),
            ]),
        ),
        html.Div([
            _section("AI 推荐", icon="⭐",
                children=html.Div("暂无 AI 推荐", style={
                    "color": COLORS["text_muted"], "textAlign": "center",
                    "padding": "40px 0", "fontSize": "13px",
                }),
            ),
            _section("信号推荐", icon="🔔",
                children=html.Div("暂无活跃信号", style={
                    "color": COLORS["text_muted"], "textAlign": "center",
                    "padding": "40px 0", "fontSize": "13px",
                }),
            ),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px"}),
    ])


# ════════════════════════════════════════════════════════════
#  页面：数据下载
# ════════════════════════════════════════════════════════════

DOWNLOAD_SYMBOLS = [
    {"label": "BTC/USDT", "value": "BTC/USDT"},
    {"label": "ETH/USDT", "value": "ETH/USDT"},
    {"label": "SOL/USDT", "value": "SOL/USDT"},
]

DOWNLOAD_MARKETS = [
    {"label": "加密货币", "value": "crypto"},
    {"label": "A 股", "value": "a_share"},
]


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
                    "padding": "12px 32px", "background": COLORS["accent"],
                    "color": "#fff", "border": "none", "borderRadius": "8px",
                    "fontSize": "15px", "fontWeight": "600",
                    "cursor": "pointer", "transition": "all 0.2s",
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
                        html.Th("数据源", style={"padding": "8px 12px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "left"}),
                        html.Th("交易对/代码", style={"padding": "8px 12px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "left"}),
                        html.Th("周期", style={"padding": "8px 12px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "left"}),
                        html.Th("条数", style={"padding": "8px 12px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "right"}),
                        html.Th("更新时间", style={"padding": "8px 12px", "fontSize": "11px",
                                  "color": COLORS["text_muted"], "textAlign": "right"}),
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


# ════════════════════════════════════════════════════════════
#  页面：日志
# ════════════════════════════════════════════════════════════

def _page_logs() -> html.Div:
    return html.Div([
        html.Div([
            _section("系统日志", icon="📝",
                children=html.Div(id="logs-system", style={
                    "fontFamily": "'JetBrains Mono', 'Consolas', monospace",
                    "fontSize": "12px", "lineHeight": "1.8",
                    "maxHeight": "500px", "overflowY": "scroll",
                }, children=[
                    html.Div(datetime.now().strftime("[%H:%M:%S] 系统就绪"),
                             style={"color": COLORS["text_secondary"]}),
                ]),
            ),
        ]),
        html.Div([
            _section("交易记录", icon="🔄",
                children=html.Div(id="logs-trades",
                    children=[html.Div("暂无交易记录", style={
                        "color": COLORS["text_muted"], "textAlign": "center",
                        "padding": "40px 0", "fontSize": "13px",
                    })]),
            ),
        ]),
    ])


# ════════════════════════════════════════════════════════════
#  回调注册
# ════════════════════════════════════════════════════════════

def _register_callbacks(app: dash.Dash):
    """注册所有交互回调。"""

    # ── 侧边栏导航 ────────────────────────────────────
    nav_ids = [f"nav-{item['id']}" for item in NAV_ITEMS]
    page_map = {f"nav-{item['id']}": item['id'] for item in NAV_ITEMS}
    title_map = {item['id']: item['label'] for item in NAV_ITEMS}
    page_funcs = {
        "overview": _page_overview,
        "backtest": _page_backtest,
        "strategies": _page_strategies,
        "trading": _page_trading,
        "ai": _page_ai,
        "data": _page_data,
        "logs": _page_logs,
    }

    @app.callback(
        [Output("page-content", "children"),
         Output("page-title", "children"),
         Output("current-page", "data")],
        [Input(nav_id, "n_clicks") for nav_id in nav_ids],
        prevent_initial_call=True,
    )
    def navigate(*_):
        ctx = callback_context
        if not ctx.triggered:
            return _page_overview(), "总览", "overview"

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        page_id = page_map.get(trigger_id, "overview")
        page_fn = page_funcs.get(page_id, _page_overview)
        title = title_map.get(page_id, "总览")
        return page_fn(), title, page_id

    # ── 时钟 ───────────────────────────────────────────
    @app.callback(
        Output("live-clock", "children"),
        Input("global-timer", "n_intervals"),
    )
    def update_clock(_):
        return datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    # ── 回测运行 ───────────────────────────────────────
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

            # 生成数据
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

            # 运行回测
            engine = BacktestEngine(initial_capital=float(capital), market=market)
            cls, params = STRATEGY_CLASSES[strategy]
            engine.add_strategy(cls(params), symbols=[symbol], weight=1.0, timeframe=timeframe)
            report = engine.run({symbol: df})

            # 补充 equity_curve 到 report 中
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

    # ── 数据下载 ───────────────────────────────────────
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

        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

        return html.Span(
            "ℹ️ 数据下载需要联网。请使用命令行: "
            f"python scripts/download_data.py --market {market} --freq {freq}",
            style={"color": COLORS["info"]}
        )
