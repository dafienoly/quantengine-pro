# QuantEngine Pro

> 全流程量化交易系统 — 数据获取 → 因子计算 → 策略研发 → 回测验证 → 实盘执行 → 监控分析

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0-orange)]()

## 核心特性

- **多市场支持**: A股（日线/分钟）+ 加密货币（现货/永续合约）
- **7+内置策略**: Dual Thrust, R Breaker, 海龟, 布林带, 双均线, 网格+MA, 做市商
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
│    Strategy Layer                    │  7+策略/因子/注册机制
├─────────────────────────────────────┤
│    Backtest Layer                    │  事件驱动回测/绩效分析
├─────────────────────────────────────┤
│    Data Layer                        │  行情/大盘/新闻/缓存
└─────────────────────────────────────┘
```

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 数据下载

```bash
# 下载加密货币数据
python scripts/download_data.py --market crypto --freq 1h --symbols BTC/USDT,ETH/USDT

# 下载A股数据
python scripts/download_data.py --market a_share --freq 1d --start 20200101 --max-symbols 100
```

### 运行回测

```bash
python scripts/run_backtest.py --strategy dual_thrust --symbol ETH/USDT --timeframe 1h
python scripts/run_backtest.py --strategy turtle --symbol BTC/USDT --timeframe 1d
python scripts/run_backtest.py --strategy bollinger --symbol ETH/USDT --timeframe 15m
```

### 启动Web看板

```bash
python -m quantengine.web.app --port 8050
# Dashboard: http://localhost:8050
# API Docs:  http://localhost:8000/docs
```

## 内置策略

| 策略 | 类型 | 描述 |
|------|------|------|
| Dual Thrust | 突破 | 前N日区间双重突破 |
| R Breaker | 突破/反转 | 昨日价格6级关键价位 |
| Turtle | 趋势 | 唐奇安通道+ATR止损 |
| Bollinger | 反转 | 布林带均值回归+RSI确认 |
| Dual MA | 趋势 | 双均线金叉死叉+网格 |
| Grid+MA | 网格 | MA趋势过滤的网格交易 |
| Simple MM | 做市 | 中间价双侧限价单 |

## 配置

所有配置通过 `config/` 目录下的YAML文件管理：

- `data_source.yaml` - 数据源（akshare/CCXT/EastMoney）
- `llm.yaml` - LLM配置（DeepSeek/OpenAI）
- `strategies.yaml` - 策略列表及参数
- `risk_config.yaml` - 风控阈值
- `execution.yaml` - 执行配置

## 项目结构

```
quantengine/
├── config/          # 配置管理
├── data/            # 数据层（行情/缓存/存储）
├── factor/          # 因子系统
├── strategy/        # 策略层（基类+内置策略）
├── backtest/        # 回测引擎
├── execution/       # 执行层（券商/风控/报告）
├── analysis/        # 分析服务（LLM/选股/信号）
├── web/             # Web展示（FastAPI+Dash）
└── utils/           # 工具（日志）
```

## 设计原则

1. **分层解耦**: 各层通过抽象接口交互
2. **插件化**: 数据源/券商/LLM可通过配置切换
3. **事件驱动**: 严格按市场数据→信号→订单→成交→持仓更新
4. **全成本**: 佣金/印花税/滑点/融资利息全部纳入
5. **免费优先**: 所有组件提供免费方案，通过配置平滑升级

## License

MIT © QuantEngine Team
