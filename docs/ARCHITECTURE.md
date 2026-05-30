# QuantEngine Pro — Architecture

## System Overview

QuantEngine Pro follows a **layered + event-driven + plugin-based** architecture.

```
┌─────────────────────────────────────────┐
│     Presentation Layer (Web UI)          │  Plotly Dash + FastAPI
│     Dashboard, Strategy Monitor, Report  │
└───────────────────┬─────────────────────┘
                    │ REST / WebSocket
┌───────────────────┴─────────────────────┐
│     Analysis Service Layer               │
│     Market Overview, LLM, Screener       │
└───────────────────┬─────────────────────┘
                    │ Internal API
┌───────────────────┴─────────────────────┐
│     Execution Layer                      │
│     Order Manager, Risk, Position        │
└───────────────────┬─────────────────────┘
                    │ Event Bus
┌───────────────────┴─────────────────────┐
│     Strategy Layer                       │
│     Strategy Engine, 9 Built-in Strategies│
└───────────────────┬─────────────────────┘
                    │ Unified Data Context
┌───────────────────┴─────────────────────┐
│     Backtest & Simulation Layer          │
│     Event-Driven Engine, Cost Model      │
└───────────────────┬─────────────────────┘
                    │ Market Data Stream
┌───────────────────┴─────────────────────┐
│     Data Layer                           │
│     Fetchers, Cache, Parquet Storage     │
└─────────────────────────────────────────┘
```

## Layer Responsibilities

### Data Layer (`quantengine/data/`)
- **Base abstractions**: `BaseQuoteFetcher`, `BaseMarketFlowFetcher`, `BaseNewsFetcher`
- **Implementations**: Akshare (A-share), CCXT (crypto), EastMoney (fund flow)
- **Cache**: 3-tier (LRU memory → Redis → Parquet)
- **Storage**: Partitioned Parquet files

### Backtest Layer (`quantengine/backtest/`)
- **EventBus**: 12 event types, synchronous dispatch
- **Engine**: Event-driven main loop per bar
- **Broker**: Order validation, multi-strategy capital competition
- **CostModel**: Commission, stamp tax, slippage (3 models), financing
- **PositionManager**: Margin tracking, forced liquidation, equity curve
- **Analyzer**: Sharpe, Sortino, Calmar, VaR, CVaR, profit factor, monthly heatmap

### Strategy Layer (`quantengine/strategy/`)
- **BaseStrategy**: `on_bar()`, `on_tick()` interface
- **Signal**: Standardized signal with price, stop-loss, take-profit, confidence
- **Registry**: Dynamic loading from YAML config, hot-reload
- **9 strategies**: Dual Thrust, R Breaker, Turtle, Bollinger, Dual MA, Grid+MA, Simple MM, Panic Reversal, Low Vol Defense

### Execution Layer (`quantengine/execution/`)
- **BaseBrokerClient**: Abstract interface for all brokers
- **CCXTClient**: 100+ crypto exchanges, testnet support
- **QMTClient**: A-share via QMT terminal, simulation mode
- **RiskManager**: Position limits, daily loss circuit breaker, blacklist
- **Executor**: Scan → signal → risk → order loop
- **Reporter**: Daily reports with log/email/DingTalk/WeChat adapters

### Analysis Layer (`quantengine/analysis/`)
- **MarketOverview**: Breadth, fear & greed index, sector flow
- **LLM**: Base interface + DeepSeek adapter (OpenAI-compatible)
- **Screener**: 5 screen conditions + LLM news filtering
- **SignalAdvisor**: Strategy + pattern + LLM → recommendation

### Web Layer (`quantengine/web/`)
- **FastAPI**: 8 REST endpoints + WebSocket streaming
- **Dash**: 5-tab dashboard (Overview, Strategies, Backtest, AI, Logs)

## Design Principles

1. **Interface Segregation**: All components interact through abstract interfaces
2. **Plugin Architecture**: Data sources, brokers, LLM providers are pluggable
3. **Event-Driven**: Backtest follows MARKET_DATA → SIGNAL → ORDER → FILL → POSITION_UPDATE
4. **Full Cost Simulation**: Commission, stamp tax, slippage, financing all modeled
5. **Free-First, Upgrade-Ready**: Free data sources and LLM by default, config-driven upgrade path

## Data Flow (Backtest)

```
Historical Data (Parquet)
        │
        ▼
  [BacktestEngine.run()]
        │
        ├──► MARKET_DATA event published
        │         │
        │         ▼
        │    Strategy.on_bar() called for each strategy
        │         │
        │         ▼
        │    Signal(s) generated
        │         │
        │         ▼
        │    Broker.submit_signals() validates & creates orders
        │         │
        │         ▼
        │    Broker.fill_orders() executes at bar close price
        │         │
        │         ▼
        │    CostModel calculates transaction costs
        │         │
        │         ▼
        │    PositionManager updates positions & equity
        │         │
        │         ▼
        │    Risk events checked (stop-loss, margin call)
        │         │
        │         ▼
        │    BAR_CLOSE event → equity recorded
        │
        ▼
  [PerformanceAnalyzer] generates report
```

## Configuration System

All configs in `config/*.yaml`:
- `data_source.yaml` — Data provider selection (akshare/CCXT/EastMoney)
- `llm.yaml` — LLM config (DeepSeek/OpenAI/Anthropic)
- `strategies.yaml` — Active strategies with parameters
- `risk_config.yaml` — Risk thresholds
- `execution.yaml` — Broker, costs, notifications

Environment variables: `${VAR_NAME}` syntax in YAML files resolved at load time.
