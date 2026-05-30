# QuantEngine Pro

> 全流程量化交易系统 — 数据获取 → 因子计算 → 策略研发 → 回测验证 → 实盘执行 → 监控分析

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0-orange)]()

## 核心特性

- **多市场支持**: A股（日线/分钟）+ 加密货币（现货）
- **10个内置策略**: Dual Thrust, R Breaker, 海龟, 布林带, 双均线, 网格+MA, 做市商, 恐慌反转, 低波动防御, 多因子选股
- **事件驱动回测**: 全成本模拟（佣金/印花税/滑点/融资利息）
- **多因子系统**: 动量/波动率/成交量/RSI/MACD 等可扩展因子库
- **LLM增强**: DeepSeek AI进行新闻情感分析、市场解读、买卖点推荐
- **实盘执行**: 风控模块（仓位限制/日亏损熔断/强制平仓）
- **Web看板**: Plotly Dash 可视化（权益曲线/持仓/信号/AI分析）
- **免费起步**: akshare + CCXT + DeepSeek免费API，零成本验证策略

## 架构

```
┌─────────────────────────────────────┐
│    Presentation Layer (Web UI)       │  Plotly Dash + FastAPI
├─────────────────────────────────────┤
│    Analysis Service Layer            │  LLM分析/选股/信号推荐
├─────────────────────────────────────┤
│    Execution Layer                   │  实盘执行/风控/报告
├─────────────────────────────────────┤
│    Strategy Layer                    │  10策略/因子/注册机制
├─────────────────────────────────────┤
│    Backtest Layer                    │  事件驱动回测/绩效分析
├─────────────────────────────────────┤
│    Data Layer                        │  行情/大盘/新闻/缓存
└─────────────────────────────────────┘
```

---

## 🚀 部署与启动

本系统支持两种运行模式：

> **本地开发** — 直接使用 Python 虚拟环境，适合策略研发和回测
> **Docker 生产** — 容器化部署，包含 Redis 缓存和定时数据下载，适合长期运行

---

### 🔧 前置要求

| 组件 | 本地开发 | Docker 生产 |
|------|----------|-------------|
| Python | ≥ 3.10 | — (已内置在镜像中) |
| Docker | — | Docker Engine 24+ |
| 内存 | ≥ 2 GB | ≥ 4 GB |
| API Key | DeepSeek (免费) | DeepSeek (免费) |

> **获取 DeepSeek API Key**（免费）：https://platform.deepseek.com/api_keys

---

### ⚙️ 环境变量配置

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env，填入你的 API Key
#    至少需要 DEEPSEEK_API_KEY
```

`.env` 文件内容示例：

```bash
# 必填：DeepSeek API Key（免费）
DEEPSEEK_API_KEY=sk-your-key-here

# 可选：备用 LLM
# OPENAI_API_KEY=sk-xxx
```

> **注意**：本地开发时如果仅使用回测和模拟交易，可以不配置 API Key（LLM 分析功能不可用，其余功能正常）。

---

### 📦 方式一：本地开发环境

适合策略研发、回测验证、快速调试。

#### 一键安装（推荐）

项目根目录下有一键安装脚本 `setup.py`，自动完成创建虚拟环境、安装依赖、运行测试：

```bash
# 完整安装（含 akshare、ccxt 等，预计 2-5 分钟）
python setup.py

# 最小安装（仅核心依赖，仅加密货币场景）
python setup.py --minimal

# 跳过测试（快速部署，后续再验证）
python setup.py --skip-test
```

**Windows PowerShell** 中直接运行：

```powershell
python setup.py
```

**Linux / macOS** 同样：

```bash
python3 setup.py
```

#### 分步安装（可选）

如需手动控制每一步：

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov black ruff

# 4. 验证
python -m pytest tests/ -v --tb=short
```

#### 4. 下载数据

```bash
# 加密货币（BTC/USDT, ETH/USDT 1小时线）
python scripts/download_data.py --market crypto --freq 1h --symbols BTC/USDT,ETH/USDT

# A 股（前 200 只股票，日线，从 2020 年起）
python scripts/download_data.py --market a_share --freq 1d --start 20200101 --max-symbols 200
```

#### 5. 运行回测

```bash
# 单策略回测
python scripts/run_backtest.py --strategy dual_thrust --symbol ETH/USDT --timeframe 1h

# 回测所有策略（生成对比报告）
make backtest-all

# 参数优化（使用 Optuna）
python scripts/optimize.py --strategy dual_thrust --objective sharpe
```

#### 6. 启动 Web 看板

```bash
# 一键启动（Dash 仪表盘 + FastAPI 后端 + WebSocket）
make dashboard

# 或在激活 venv 后直接运行：
python -m quantengine.web.app --port 8050
```

然后打开浏览器：

| 地址 | 用途 |
|------|------|
| http://localhost:8050 | 📊 Dash 仪表盘（权益曲线/持仓/AI分析） |
| http://localhost:8000/docs | 📑 FastAPI Swagger 文档 |

---

### 🐳 方式二：Docker 生产部署

适合服务器长期运行，包含 Redis 缓存、日志轮转、资源限制、健康检查。

#### 1. 准备环境

```bash
# 确保 .env 文件已配置（至少包含 DEEPSEEK_API_KEY）
# Docker Compose 会自动读取 .env 文件中的变量
```

#### 2. 构建与启动

```bash
# 构建镜像并启动所有服务
docker compose up -d

# 查看启动日志
docker compose logs -f app
```

#### 3. 服务架构

启动后的容器：

| 容器名 | 镜像 | 端口 | 用途 |
|--------|------|------|------|
| `quantengine-app` | `quantengine-pro:latest` | `8050` / `8000` | Web 仪表盘 + API |
| `quantengine-redis` | `redis:7-alpine` | `6379` | 缓存加速 |

#### 4. 可选：启用数据自动下载

```bash
# 额外启动数据下载服务（每小时自动拉取）
docker compose --profile full up -d
```

这会在上述基础上额外启动：

| 容器名 | 用途 |
|--------|------|
| `quantengine-downloader` | 每小时自动下载 BTC/USDT, ETH/USDT 1h 数据 |

#### 5. 生产管理命令

```bash
# 查看服务状态
docker compose ps

# 查看日志（实时）
docker compose logs -f app

# 查看 Redis 日志
docker compose logs -f redis

# 停止所有服务
docker compose down

# 重新构建并启动（代码变更后）
docker compose up -d --build
```

#### 6. 资源限制

默认资源配置（在 `docker-compose.yml` 中可调整）：

| 服务 | 内存限制 | 预留内存 |
|------|----------|----------|
| app | 2 GB | 512 MB |
| data-downloader | 1 GB | 256 MB |

---

## 📋 Makefile 速查

```bash
make help          # 显示所有可用命令

# 环境
make install       # 安装所有依赖（venv）
make test          # 运行全部测试（12项）
make test-cov      # 测试 + 覆盖率报告
make test-smoke    # 快速冒烟测试

# 数据
make download-crypto   # 下载加密货币数据
make download-ashare   # 下载 A 股数据

# 回测
make backtest         # 运行示例回测（Dual Thrust）
make backtest-all     # 回测所有策略

# Web
make dashboard        # 启动 Web 看板
make api              # 仅启动 API 服务

# Docker
make docker-build     # 构建镜像
make docker-up        # 启动 Docker 服务
make docker-up-full   # 启动完整服务（含数据下载）
make docker-down      # 停止
make docker-logs      # 查看日志

# 代码质量
make lint             # 代码检查（ruff）
make lint-fix         # 自动修复
make format           # 格式化（black）

# 清理
make clean            # 清理缓存文件
make clean-all        # 深度清理（含 venv + 数据）
```

---

## 🧪 测试体系

| 测试 | 文件 | 内容 | 数量 |
|------|------|------|------|
| 冒烟测试 | `tests/smoke_test.py` | 模块导入、配置解析、完整回测流程 | 3 |
| 压力测试 | `tests/test_stress.py` | 10K 数据集、多策略并行、闪电崩盘场景、风控边界、事件吞吐量、大规模因子计算 | 9 |

```bash
# 运行全部测试
make test

# 仅冒烟测试
make test-smoke

# 带覆盖率
make test-cov
# 结果在 htmlcov/index.html
```

---

## 🧩 内置策略

| 策略 | 类型 | 文件 | 描述 |
|------|------|------|------|
| Dual Thrust | 突破 | `dual_thrust.py` | 前N日区间双重突破，经典日内策略 |
| R Breaker | 突破/反转 | `r_breaker.py` | 基于昨日价格的6级关键价位，日内交易 |
| Turtle | 趋势 | `turtle.py` | 唐奇安通道入场 + ATR 浮动止损 |
| Bollinger | 反转 | `bollinger.py` | 布林带均值回归 + RSI 过滤确认 |
| Dual MA | 趋势 | `dual_ma.py` | 双均线金叉死叉 + 网格仓位管理 |
| Grid+MA | 网格 | `grid_ma.py` | MA 趋势方向过滤的网格交易 |
| Simple MM | 做市 | `simple_mm.py` | 中间价双侧限价单，赚取买卖价差 |
| Panic Reversal | 反转 | `panic_reversal.py` | 恐慌性下跌检测 + 反转确认入场 |
| Low Vol Defense | 防御 | `low_vol_defense.py` | 高波动率防御模式，自动减仓 |
| Multi-Factor | 选股 | `multi_factor.py` | 多因子评分选股，支持动量/波动率/RSI等 |
| Sector Rotation | 轮动 | `sector_rotation.py` | 板块动量轮动，定期调仓 |

---

## ⚙️ 配置详解

所有配置集中管理在 `config/` 目录：

| 文件 | 用途 | 关键参数 |
|------|------|----------|
| `data_source.yaml` | 数据源配置 | `quote.provider` (akshare/ccxt), `storage.parquet_path` |
| `llm.yaml` | LLM 配置 | `provider` (deepseek/openai), `model`, `api_key` (从环境变量读取) |
| `strategies.yaml` | 策略注册 | 启用/禁用策略及各策略参数 |
| `risk_config.yaml` | 风控阈值 | `max_single_symbol_pct: 0.20`, 连续亏损熔断, 黑名单 |
| `execution.yaml` | 执行配置 | 券商选择、成本模型、通知渠道 |

环境变量引用：YAML 中支持 `${VAR_NAME}` 和 `${VAR_NAME:default}` 语法。

---

## 📁 项目结构

```
quantengine/
├── config/              # 配置管理（YAML + 环境变量解析）
├── data/                # 数据层
│   ├── base.py          #   数据源 ABC
│   ├── akshare_fetcher.py   # A 股行情
│   ├── ccxt_fetcher.py      # 加密货币行情
│   ├── eastmoney_fetcher.py  # 资金流向
│   ├── news_fetcher.py       # 新闻抓取
│   ├── cache.py              # 三级缓存（LRU → Redis → Parquet）
│   └── storage.py            # Parquet 文件存储
├── backtest/            # 回测引擎
│   ├── engine.py        #   事件驱动主循环
│   ├── broker.py        #   订单执行、多策略资金竞争
│   ├── cost_model.py    #   全成本模拟
│   ├── position_manager.py  # 持仓管理、强平
│   ├── analyzer.py      #   绩效分析（夏普/回撤/Calmar）
│   └── event_bus.py     #   事件总线
├── strategy/            # 策略层
│   ├── base.py          #   BaseStrategy ABC
│   ├── registry.py      #   动态注册/加载
│   └── builtin/         #   10 个内置策略
├── factor/              # 因子系统
│   └── base.py          #   动量/波动率/RSI/MACD 因子库
├── execution/           # 执行层
│   ├── base.py          #   BrokerClient ABC
│   ├── ccxt_client.py   #   加密交易所对接
│   ├── qmt_client.py    #   A 股 QMT 对接
│   ├── executor.py      #   扫描→信号→订单循环
│   ├── risk_manager.py  #   风控引擎
│   └── reporter.py      #   日报生成（Log/DingTalk/WeChat）
├── analysis/            # 分析服务
│   ├── llm/             #   DeepSeek / OpenAI 适配器
│   ├── screener.py      #   自动选股
│   └── signal_advisor.py # 买卖信号推荐
├── web/                 # Web 展示
│   ├── api.py           #   FastAPI REST + WebSocket
│   ├── dashboard.py     #   Plotly Dash 5面板
│   └── app.py           #   启动入口
└── utils/               # 工具
    └── logging.py       #   Loguru 日志配置
```

---

## 🛠️ 常见问题

**Q: 启动 Dashboard 报错 `ModuleNotFoundError`**

确保已激活虚拟环境并安装了所有依赖：

```bash
venv\Scripts\activate   # Windows
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

**Q: Docker 启动后访问 localhost:8050 显示空白**

首次构建需要下载依赖，等待 1-2 分钟后刷新：

```bash
docker compose logs -f app  # 查看构建日志
```

**Q: 是否需要配置 API Key 才能使用？**

- **不需要** — 回测、数据下载、策略开发完全离线可用
- LLM 分析功能（AI 看板、信号推荐）需要 `DEEPSEEK_API_KEY`

**Q: Redis 未安装是否影响使用？**

不影响。本地开发时 Redis 不可用，系统自动降级为内存 + Parquet 缓存，仅输出一条 `WARNING` 日志。

**Q: Windows `python` 命令找不到？**

请从 https://python.org 安装 Python 3.10+，安装时勾选 "Add Python to PATH"。

---

## 📚 参考文档

| 文档 | 位置 | 内容 |
|------|------|------|
| 架构文档 | `docs/ARCHITECTURE.md` | 6层架构详解、数据流图、设计原则 |
| 任务计划 | `task_plan.md` | 5阶段实现计划（57项） |
| 调研记录 | `findings.md` | 技术选型决策依据 |

---

## 设计原则

1. **分层解耦**: 各层通过抽象接口交互，可独立替换实现
2. **插件化**: 数据源/券商/LLM 可通过 YAML 配置切换，无需改代码
3. **事件驱动**: 严格按 MARKET_DATA → SIGNAL → ORDER → FILL → POSITION_UPDATE 事件流执行
4. **全成本**: 佣金/印花税/滑点/融资利息全部纳入模拟
5. **免费优先**: akshare + CCXT + DeepSeek 免费 API 提供完整功能，付费方案可通过配置平滑升级

## License

MIT © QuantEngine Team
