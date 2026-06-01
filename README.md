# QuantEngine Pro 量化引擎专业版

> 全流程量化交易系统 — 数据获取 → 因子计算 → 策略研发 → 回测验证 → 实盘执行 → AI 监控分析

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0-orange)]()
[![Code style](https://img.shields.io/badge/code%20style-black-000000)]()

**一键启动，开箱即用** — 无需任何 API Key 即可查看 A股 + 美股 + 加密货币实时行情。

---

## 📋 目录

- [核心特性](#-核心特性)
- [系统架构](#-系统架构)
- [功能全景图](#-功能全景图)
- [三层数据流](#-三层数据流)
- [16 个内置策略](#-16-个内置策略)
- [快速开始](#-快速开始)
- [配置指南](#-配置指南)
- [Web 仪表盘](#-web-仪表盘)
- [API 参考](#-api-参考)
- [项目结构](#-项目结构)
- [开发指南](#-开发指南)
- [常见问题](#-常见问题)

---

## ✨ 核心特性

### 多市场全覆盖
| 市场 | 数据源 | 费用 | 数据粒度 |
|------|--------|------|---------|
| 🇨🇳 A股 | akshare（东方财富） | ✅ 免费 | Tick / 1m~日线 |
| 🇺🇸 美股 | akshare（东方财富） | ✅ 免费 | 实时报价 |
| 💎 加密货币 | CCXT（Binance） | ✅ 免费 | Tick / 1m~周线 |

### 16 个内置策略
突破、趋势、反转、复合、因子、做市六大类，覆盖主流量化策略。

### 事件驱动回测引擎
- 全成本模拟：佣金 / 印花税 / 滑点 / 融资利息
- 多策略资金竞争：权重分配，资金上限
- 强制平仓：杠杆维持保证金率 < 130% 触发
- 绩效分析：夏普 / 索提诺 / 最大回撤 / Calmar / 月度热力图

### AI 增强分析
- 🔗 **LLM 新闻情感分析** — DeepSeek / OpenAI 分析新闻情感，输出买入/卖出信号
- 📊 **AI 选股** — 多条件筛选 + 因子排名 + LLM 过滤
- 💡 **买卖点推荐** — 策略信号 + 技术形态 + LLM 解释

### Web 可视化仪表盘
- 8 个功能页面，侧边栏导航
- 实时 A股 + 美股 + 加密货币行情（每 5 秒刷新）
- 在线回测：选择策略 → 一键运行 → 权益曲线 + 交易明细
- AI 新闻分析：点击按钮抓取新闻 → LLM 分析 → 展示情感趋势
- API Key 配置：DeepSeek / OpenAI / Anthropic 界面配置

### 免费起步，平滑升级
| 服务 | 免费方案 | 升级方案 |
|------|---------|---------|
| 行情数据 | akshare + CCXT | QMT / Tushare Pro |
| 大盘数据 | 东方财富网页 API | Wind / iFinD |
| 新闻 | 财联社 RSS / CryptoPanic | Bloomberg / Reuters |
| LLM | DeepSeek API（免费额度） | GPT-4 / Claude |

---

## 🏗 系统架构

采用**分层 + 事件驱动 + 插件化**架构，各层通过抽象接口交互。

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│          Web Dashboard · REST API · WebSocket               │
│       Plotly Dash + FastAPI + Plotly Charting               │
├─────────────────────────────────────────────────────────────┤
│                    Analysis Service Layer                    │
│   LLM News Analyzer · Stock Screener · Signal Advisor      │
│   DeepSeek / OpenAI / Anthropic · Sentiment Pipeline        │
├─────────────────────────────────────────────────────────────┤
│                    Execution Layer                           │
│   Live Executor · Risk Manager · Daily Reporter             │
│   QMT Client (A股) · CCXT Broker (Crypto)                  │
├─────────────────────────────────────────────────────────────┤
│                    Strategy Layer                            │
│   Strategy Engine · 16 Built-in Strategies · Registry       │
│   Factor System · Custom Strategy Loader                    │
├─────────────────────────────────────────────────────────────┤
│                    Backtest Layer                            │
│   Event-Driven Engine · Multi-Strategy Competition          │
│   Cost Model · Position Manager · Performance Analyzer      │
├─────────────────────────────────────────────────────────────┤
│                    Data Layer                                │
│   Quote Fetcher · Market Flow Fetcher · News Fetcher       │
│   3-Tier Cache (Memory LRU + Redis + Parquet)              │
│   Factor Library · Auto-calculation Pipeline                │
└─────────────────────────────────────────────────────────────┘
```

### 各层职责

#### 数据层 (Data Layer)
- **行情获取**: `BaseQuoteFetcher` 抽象 → `AkshareQuoteFetcher`（A 股）/ `CCXTQuoteFetcher`（加密货币）
- **大盘资金流**: `BaseMarketFlowFetcher` → `EastMoneyFlowFetcher`
- **新闻获取**: `BaseNewsFetcher` → `CailianNewsFetcher` / `SinaStockNewsFetcher` / `CryptoPanicNewsFetcher`
- **三级缓存**: 内存 LRU（1000 项）→ Redis（7 天）→ Parquet（永久）
- **因子计算**: 数据加载后自动触发，因子结果合并入标准 DataFrame

#### 回测层 (Backtest Layer)
- 事件驱动引擎：严格按 `市场数据 → 策略信号 → 订单 → 成交 → 持仓更新` 顺序处理
- 全成本模拟：佣金（比例/固定）、印花税（卖出 0.1%）、滑点（固定/比例/成交量）、融资利息
- 多策略资金竞争：权重分配，资金上限，订单按优先级和资金上限撮合
- 强制平仓：维持保证金率 < 130% 触发强平

#### 策略层 (Strategy Layer)
- `BaseStrategy` 抽象：需实现 `on_bar()` / `on_tick()` 产生 `Signal`
- `Signal` 含：timestamp, symbol, type, price, quantity, stop_loss, take_profit, confidence, metadata
- 通过 YAML 注册策略，启动时动态加载，支持热更新
- 16 个内置策略覆盖六大类交易逻辑

#### 执行层 (Execution Layer)
- `BaseBrokerClient` 统一接口：`place_order` / `cancel_order` / `get_positions` / `get_balance`
- 主循环每隔 10 秒扫描策略标的 → 信号生成 → 风控检查 → 下单
- 订单超时自动取消，部分成交自动追单
- 风控模块：单标的 ≤ 20% / 总仓位 ≤ 95% / 日亏损 ≥ 5% 熔断 / 连续亏损 5 笔暂停

#### 分析服务层 (Analysis Service Layer)
- LLM 新闻分析：聚合新闻 → 去重 → LLM 情感分析 → 结构化结果
- 自动选股：技术面 + 基本面 + 因子排名 + LLM 新闻过滤
- 买卖点推荐：策略信号 + 技术形态 + LLM 解读

#### 展示层 (Presentation Layer)
- FastAPI 提供 REST + WebSocket 接口
- Plotly Dash 构建 8 页面 Web 仪表盘
- 实时行情每 5 秒自动刷新

---

## 🗺 功能全景图

| 领域 | 模块 | 关键能力 | 免费数据源 | 升级路径 |
|------|------|---------|-----------|---------|
| **数据** | 行情获取 | A股/美股/加密货币 Tick/Min/日K | akshare + CCXT | QMT / Tushare Pro |
| | 大盘资金流 | 市场宽度、板块资金、指数估值 | 东方财富免费 API | Wind / iFinD |
| | 新闻舆情 | 财联社、新浪财经、币圈快讯 | 财联社 RSS、CryptoPanic | Bloomberg / Reuters |
| | 数据缓存 | 三级缓存策略 | Parquet + Redis | Redis Cluster |
| | 因子计算 | 技术/基本面/另类因子 | 基于缓存实时计算 | 自定义因子 SDK |
| **回测** | 事件驱动引擎 | 全成本逐笔复利 | 自研 | 分布式回测 |
| | 绩效分析 | 夏普/回撤/Calmar/月度热力图 | 自研 + Optuna | — |
| **策略** | 经典策略库 | 16 个策略 | 内置 | 自定义策略 SDK |
| | 因子策略 | 多因子选股、行业轮动 | 内置 | 自定义因子 |
| **执行** | 实盘执行器 | QMT/CCXT 统一执行 | — | 多券商 |
| | 风控 | 仓位限制/日亏损熔断 | 内置 | — |
| | 报告 | 每日自动报告 | 邮件适配器 | 钉钉/微信 |
| **分析** | LLM 新闻分析 | 新闻→情感→标的评分 | DeepSeek | GPT-4 / Claude |
| | 自动选股 | 多条件 + 因子 + LLM | 内置 | — |
| **展示** | Web 看板 | 8 页面仪表盘 | Plotly Dash | — |

---

## 📊 三层数据流

### 第一层：实时行情（零配置，自动刷新）

```
┌──────────┐    ┌──────────────┐    ┌─────────────────┐
│ Binance  │───▶│  CCXT 公开API │───▶│  market-data-   │
│ 交易所   │    │  (免费, 无需  │    │  store (每5秒)  │
│          │    │   API Key)    │    │                  │
├──────────┤    ├──────────────┤    ├─────────────────┤
│ 东方财富 │───▶│  akshare     │───▶│  顶栏行情条     │
│ (A股+美股)│   │  (免费)       │    │  ticker-bar     │
└──────────┘    └──────────────┘    └─────────────────┘
```

首次启动立即展示 BTC/USDT、ETH/USDT、上证指数、沪深300、标普500 等实时价格。网络不可用时自动降级为模拟行情，UI 始终有数据。

### 第二层：在线回测（界面配置，一键运行）

```
选择策略 → 配置参数 → 点击运行
  │
  ├─ 生成模拟行情数据
  ├─ BacktestEngine.run()
  ├─ 权益曲线 + 交易明细
  └─ 绩效指标报表
```

所有 16 个策略均可从 Web 界面直接回测，无需编辑任何代码。

### 第三层：AI 新闻分析（需配置 API Key）

```
点击「获取最新新闻并分析」
  │
  ├─ CailianNewsFetcher (免费)
  ├─ → 8 条最新财经新闻
  ├─ DeepSeek LLM 逐条分析
  │    情感分类 + 评分 + 摘要
  ├─ → 情感趋势图
  ├─ → AI 推荐 + 交易信号
  └─ → 分析结果列表
```

---

## 📈 16 个内置策略

### 突破策略

| 策略 | 核心逻辑 | 参数 |
|------|---------|------|
| **Dual Thrust** | N 日区间突破 | `k1`, `k2`, `period` |
| **R Breaker** | 前日高低点计算关键价位 | `f1`, `f2`, `f3` |
| **Aberration** | 波动率自适应布林带通道 | `period`, `num_std` |
| **菲阿里四价** | 昨高/昨低/开盘/收盘四价突破 | `atr_mult_sl`, `atr_mult_tp` |
| **动态突破 II** | ATR 动态调整回溯周期 | `base_period`, `k1`, `k2` |

### 趋势策略

| 策略 | 核心逻辑 | 参数 |
|------|---------|------|
| **海龟交易** | 唐奇安通道突破 + ATR 止损 | `entry_period`, `exit_period`, `atr_period` |
| **双均线 + 网格** | 金叉死叉 + 网格分层 | `fast_period`, `slow_period`, `grid_spacing` |
| **Pivot Point** | 枢轴点支撑阻力系统 | `sensitivity` |

### 反转策略

| 策略 | 核心逻辑 | 参数 |
|------|---------|------|
| **布林带均值回归** | 触碰上下轨反向开仓 | `period`, `num_std`, `rsi_period` |
| **RSI 反转** | 超买超卖阈值反转 | `rsi_period`, `oversold`, `overbought` |

### 复合策略

| 策略 | 核心逻辑 | 参数 |
|------|---------|------|
| **恐慌反转** | 大跌后情绪修复 | `drop_threshold`, `recovery_factor` |
| **低波防御** | 低波动组合避险 | `volatility_window`, `volatility_threshold` |

### 因子策略

| 策略 | 核心逻辑 | 参数 |
|------|---------|------|
| **多因子选股** | 动量 + 波动率 + RSI 等权打分 | `factors` |
| **行业轮动** | 动量最强的行业 ETF | `rotation_period`, `top_n` |

### 做市策略

| 策略 | 核心逻辑 | 参数 |
|------|---------|------|
| **简单做市商** | 中间价双侧挂限价单 | `spread`, `order_size`, `max_position` |

---

## 🚀 快速开始

### 前置要求

| 组件 | 版本要求 |
|------|---------|
| Python | ≥ 3.10 |
| pip | 最新版 |
| Git | — |

### 方式一：一键安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/dafienoly/quantengine-pro.git
cd quantengine-pro

# 创建虚拟环境（Python 3.10+）
python -m venv venv

# 激活环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
python -m pip install -r requirements.txt

# 一键安装 + 测试
python setup.py
```

### 方式二：Docker 生产部署

```bash
# 1. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 2. 启动
docker compose up -d

# 3. 查看日志
docker compose logs -f app
```

### 启动系统

```bash
# 启动 Web 仪表盘
python -m quantengine.web.app

# 打开浏览器访问
# http://localhost:8050
```

启动后自动展示：
- 💎 BTC/USDT + ETH/USDT 实时价格
- 🇨🇳 上证指数 + 沪深300 + 贵州茅台
- 🇺🇸 标普500 + 纳斯达克 + 苹果

全部零配置，无需任何 API Key。

---

## ⚙️ 配置指南

### 配置文件

系统所有配置集中在 `config/` 目录，YAML 格式：

```
config/
├── data_source.yaml    # 数据源配置（行情/大盘/新闻 Provider）
├── llm.yaml            # LLM 服务配置（DeepSeek/OpenAI/Claude）
├── strategies.yaml     # 策略注册与参数
├── risk_config.yaml    # 风控阈值
└── execution.yaml      # 执行配置（券商类型/间隔）
```

### API Key 配置

**方式一：Web 界面（推荐）**

1. 打开 http://localhost:8050
2. 点击侧边栏 ⚙️ **设置**
3. 填入 API Key，点击保存
4. 密钥自动存入系统密钥链（keyring）+ `.env` 文件

**方式二：环境变量**

```bash
# Linux/macOS
export DEEPSEEK_API_KEY=sk-your-key
export OPENAI_API_KEY=sk-your-key

# Windows PowerShell
$env:DEEPSEEK_API_KEY="sk-your-key"
```

**方式三：.env 文件**

```bash
cp .env.example .env
# 编辑 .env 填入密钥
```

### 切换数据源

编辑 `config/data_source.yaml`：

```yaml
data:
  quote:
    provider: akshare  # 可选: akshare, ccxt, qmt, tushare_pro
  news:
    provider: cailian  # 可选: cailian, sina, cryptopanich
```

---

## 🌐 Web 仪表盘

### 页面一览

| 页面 | 图标 | 功能 |
|------|------|------|
| **总览** | 📊 | A股/美股/加密货币实时行情 + KPI 卡片 + 权益曲线 |
| **回测** | 📈 | 策略选择 → 参数配置 → 一键运行 → 结果可视化 |
| **策略** | 📋 | 全部 16 个策略的中文卡片展示与参数说明 |
| **交易** | 💹 | 实盘执行器启停控制 + 实时持仓监控 |
| **AI 分析** | 🤖 | 新闻抓取 → LLM 情感分析 → 情感趋势 → 推荐信号 |
| **数据** | 📡 | 行情数据一键下载 + 已缓存数据状态 |
| **日志** | 📝 | 系统日志 + 交易记录 |
| **设置** | ⚙️ | DeepSeek / OpenAI / Anthropic API Key 配置 + 系统信息 |

### 实时行情

```
顶栏（始终可见，切换页面不丢失）:
💎 BTC $67,284  +1.2%  ETH $3,456  -0.4%
🇨🇳 上证指数 3,152  +0.3%  沪深300 3,780  +0.5%
🇺🇸 标普500 5,340  +0.8%  苹果 $192  -0.2%
```

---

## 📡 API 参考

### REST 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/equity` | GET | 权益曲线数据 |
| `/api/positions` | GET | 当前持仓 |
| `/api/trades` | GET | 交易记录 |
| `/api/strategies` | GET | 策略列表与状态 |
| `/api/market/overview` | GET | 市场概况 |
| `/api/backtest/run` | POST | 运行回测 |
| `/api/llm/analysis/{symbol}` | GET | LLM 分析报告 |

### WebSocket

```
ws://localhost:8001/ws
```

每秒推送 `{"equity": ..., "positions": [...], "timestamp": "..."}`

---

## 📁 项目结构

```
quantengine-pro/
├── quantengine/                  # 核心代码
│   ├── __init__.py
│   ├── config/                   # 配置管理器
│   │   └── manager.py
│   ├── data/                     # 数据层
│   │   ├── base.py               # 抽象基类（Quote/MarketFlow/News）
│   │   ├── akshare_fetcher.py    # A股 + 美股 数据
│   │   ├── ccxt_fetcher.py       # 加密货币数据
│   │   ├── eastmoney_fetcher.py  # 大盘资金流
│   │   ├── news_fetcher.py       # 新闻聚合
│   │   └── cache.py              # 三级缓存
│   ├── factor/                   # 因子计算
│   │   └── base.py               # 因子基类 + 内置因子
│   ├── strategy/                 # 策略层
│   │   ├── base.py               # BaseStrategy + Signal
│   │   ├── registry.py           # 策略注册中心
│   │   └── builtin/              # 16个内置策略
│   │       ├── dual_thrust.py
│   │       ├── turtle.py
│   │       ├── bollinger.py
│   │       ├── dual_ma.py
│   │       ├── r_breaker.py
│   │       ├── grid_ma.py
│   │       ├── simple_mm.py
│   │       ├── panic_reversal.py
│   │       ├── low_vol_defense.py
│   │       ├── multi_factor.py
│   │       ├── sector_rotation.py
│   │       ├── aberration.py
│   │       ├── pivot_point.py
│   │       ├── fei_ali.py
│   │       ├── dynamic_breakout_ii.py
│   │       └── rsi_reversal.py
│   ├── backtest/                 # 回测层
│   │   ├── engine.py             # 回测引擎
│   │   ├── event_bus.py          # 事件总线
│   │   ├── broker.py             # 模拟券商
│   │   ├── cost_model.py         # 成本模型
│   │   ├── position_manager.py   # 持仓管理
│   │   └── analyzer.py           # 绩效分析
│   ├── execution/                # 执行层
│   │   ├── base.py               # BrokerClient 抽象
│   │   ├── executor.py           # 实盘执行器
│   │   ├── risk_manager.py       # 风控
│   │   ├── reporter.py           # 每日报告
│   │   ├── qmt_client.py         # QMT A股客户端
│   │   └── ccxt_client.py        # CCXT 加密货币客户端
│   ├── analysis/                 # 分析服务层
│   │   ├── llm/
│   │   │   ├── base.py           # LLM 服务抽象
│   │   │   └── deepseek.py       # DeepSeek 实现
│   │   ├── market_overview.py    # 大盘指标
│   │   ├── screener.py           # 自动选股
│   │   └── signal_advisor.py     # 信号推荐
│   ├── web/                      # 展示层
│   │   ├── app.py                # FastAPI + Dash 启动入口
│   │   ├── dashboard.py          # Plotly Dash 仪表盘（1117 行）
│   │   └── api.py                # FastAPI REST + WebSocket
│   └── utils/
│       └── logging.py            # 日志配置
├── config/                       # 配置文件
│   ├── data_source.yaml
│   ├── llm.yaml
│   ├── strategies.yaml
│   ├── risk_config.yaml
│   └── execution.yaml
├── scripts/                      # 命令行工具
│   ├── run_backtest.py           # 回测 CLI
│   ├── optimize.py               # Optuna 参数优化
│   └── download_data.py          # 数据下载
├── tests/                        # 测试
│   ├── smoke_test.py             # 冒烟测试
│   └── test_stress.py            # 压力测试
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── setup.py                      # 一键安装脚本
├── requirements.txt
└── README.md
```

---

## 🧪 开发指南

### 添加新策略

```python
from quantengine.strategy.base import BaseStrategy, Signal, SignalType, StrategyContext

class MyStrategy(BaseStrategy):
    def __init__(self, params: dict = None):
        super().__init__(params)
        self.param1 = self.params.get("param1", 20)

    def on_bar(self, bar: pd.Series, context: StrategyContext) -> Signal | None:
        # 策略逻辑
        if condition:
            return Signal(
                timestamp=bar["timestamp"],
                symbol=context.symbol,
                type=SignalType.BUY,
                price=bar["close"],
            )
        return None
```

### 添加新数据源

```python
from quantengine.data.base import BaseQuoteFetcher

class MyFetcher(BaseQuoteFetcher):
    async def fetch_kline(self, symbol, freq, start_date=None, end_date=None, limit=1000):
        # 实现行情获取
        ...
```

### 运行测试

```bash
# 全量测试（12 项）
pytest tests/ -v

# 仅冒烟测试
pytest tests/smoke_test.py -v

# 仅压力测试
pytest tests/test_stress.py -v
```

---

## ❓ 常见问题

### Q: 打开页面后看不到数据？
首次加载时导航回调自动触发，约 1-2 秒后行情数据开始刷新。如持续显示"等待行情数据..."，检查网络连接是否正常。

### Q: 行情数据显示"模拟"而非"实时"？
免费数据源（东方财富、Binance 公开 API）在以下情况会降级为模拟数据：
- 网络不可用（断网）
- 数据源触发反爬机制（请求过于频繁）
- 非交易时间（A股休市）
模拟数据为真实的随机波动，不影响界面功能展示。

### Q: AI 分析提示"请配置 API Key"？
1. 点击侧边栏 ⚙️ **设置**
2. 填入 DeepSeek API Key（以 `sk-` 开头）
3. 点击保存
4. 进入 AI 分析页，点击「获取最新新闻并分析」

### Q: 如何查看回测结果？
1. 点击侧边栏 📈 **回测**
2. 选择策略、交易对、周期、初始资金
3. 点击「运行回测」
4. 结果显示：权益曲线图 + 交易明细 + 绩效指标

### Q: 如何下载历史数据？
1. 点击侧边栏 📡 **数据**
2. 选择市场（加密货币 / A 股）
3. 输入交易对符号
4. 选择周期和数据量
5. 点击「开始下载」

### Q: 实盘交易如何配置？
当前 A 股实盘支持 QMT 券商接口，加密货币支持 CCXT（Binance 等）。交易控制页面可启停实盘执行器，设置扫描周期。

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

*QuantEngine Pro v0.1.0 — 从数据到交易的全流程量化平台*
