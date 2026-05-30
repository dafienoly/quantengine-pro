# QuantEngine Pro - Task Plan

## Overview
Implement a full quantitative trading system based on design document v2.0.
Fully autonomous execution - no user questions needed.

## Phase 0: Infrastructure & Data Pipeline
- [ ] Create project directory structure
- [ ] Configuration management (YAML-based)
- [ ] Logging system
- [ ] Base abstract classes (QuoteFetcher, MarketFlowFetcher, NewsFetcher)
- [ ] AkshareQuoteFetcher implementation
- [ ] CCXTQuoteFetcher implementation
- [ ] EastMoneyFlowFetcher implementation
- [ ] CailianNewsFetcher / SinaStockNewsFetcher implementation
- [ ] Parquet storage manager
- [ ] Redis cache manager
- [ ] Data download scripts
- [ ] Self-test: verify data fetching and caching

## Phase 1: Backtest Engine + Classic Strategies
- [ ] EventBus system
- [ ] Broker simulator
- [ ] CostModel (commission, stamp tax, slippage)
- [ ] PositionManager
- [ ] Event-driven backtest engine core
- [ ] Performance analyzer (Sharpe, drawdown, Calmar, etc.)
- [ ] BaseStrategy abstract class
- [ ] Strategy registry & loader
- [ ] Dual Thrust strategy
- [ ] Bollinger Bands strategy
- [ ] Turtle Trading strategy
- [ ] R Breaker strategy
- [ ] Grid + MA strategy
- [ ] CLI backtest entry point
- [ ] Self-test: run backtest on each strategy, verify reports

## Phase 2: Factor System & Multi-Strategy Backtest
- [ ] BaseFactor abstract class
- [ ] Technical factor library (momentum, volatility, volume, etc.)
- [ ] Multi-factor stock selection strategy
- [ ] Sector rotation strategy
- [ ] Multi-strategy backtest with capital competition
- [ ] Optuna parameter optimization integration
- [ ] Self-test: run multi-factor backtest, verify optimization

## Phase 3: Live Execution & Risk Control
- [ ] BrokerClient abstract class
- [ ] QMTBrokerClient (simulation)
- [ ] CCXTBrokerClient (testnet)
- [ ] Live executor (scan → signal → order loop)
- [ ] Risk manager (position limits, daily loss limit, circuit breaker)
- [ ] Blacklist filter (ST stocks, low liquidity)
- [ ] Position tracker
- [ ] Daily report generator
- [ ] Notification adapters (email, DingTalk, WeChat)
- [ ] Self-test: run in simulation mode, verify risk constraints

## Phase 4: Analysis Service & Web Dashboard
- [ ] Market overview indicators (breadth, fund flow, fear index)
- [ ] BaseLLMService abstract class
- [ ] DeepSeek LLM adapter
- [ ] News analysis pipeline (clean → analyze → store)
- [ ] Auto stock screener
- [ ] Buy/sell signal advisor
- [ ] FastAPI backend with REST + WebSocket
- [ ] Plotly Dash dashboard
  - Overview: equity curve, positions, P&L, risk gauges
  - Strategy: signal flow, performance comparison
  - Backtest: config → run → report visualization
  - AI Analysis: sentiment timeline, word cloud, AI picks
  - Logs: system logs, trade records, alerts
- [ ] Self-test: start full system, verify all dashboard panels

## Phase 5: Polish & Extend
- [ ] Additional strategies (Panic Reversal, Low Vol Defense)
- [ ] Futures/options contract support
- [ ] Stress testing & error recovery
- [ ] Docker deployment
- [ ] Complete documentation
