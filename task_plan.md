# QuantEngine Pro - Task Plan

## Overview
Implement a full quantitative trading system based on design document v2.0.
Fully autonomous execution - no user questions needed.

## Phase 0: Infrastructure & Data Pipeline
- [x] Create project directory structure
- [x] Configuration management (YAML-based)
- [x] Logging system
- [x] Base abstract classes (QuoteFetcher, MarketFlowFetcher, NewsFetcher)
- [x] AkshareQuoteFetcher implementation
- [x] CCXTQuoteFetcher implementation
- [x] EastMoneyFlowFetcher implementation
- [x] CailianNewsFetcher / SinaStockNewsFetcher implementation
- [x] Parquet storage manager
- [x] Redis cache manager
- [x] Data download scripts
- [x] Self-test: verify data fetching and caching

## Phase 1: Backtest Engine + Classic Strategies
- [x] EventBus system
- [x] Broker simulator
- [x] CostModel (commission, stamp tax, slippage)
- [x] PositionManager
- [x] Event-driven backtest engine core
- [x] Performance analyzer (Sharpe, drawdown, Calmar, etc.)
- [x] BaseStrategy abstract class
- [x] Strategy registry & loader
- [x] Dual Thrust strategy
- [x] Bollinger Bands strategy
- [x] Turtle Trading strategy
- [x] R Breaker strategy
- [x] Grid + MA strategy
- [x] CLI backtest entry point
- [x] Self-test: run backtest on each strategy, verify reports

## Phase 2: Factor System & Multi-Strategy Backtest
- [x] BaseFactor abstract class
- [x] Technical factor library (momentum, volatility, volume, etc.)
- [x] Multi-factor stock selection strategy
- [x] Sector rotation strategy
- [x] Multi-strategy backtest with capital competition
- [x] Optuna parameter optimization integration
- [x] Self-test: run multi-factor backtest, verify optimization

## Phase 3: Live Execution & Risk Control
- [x] BrokerClient abstract class
- [x] QMTBrokerClient (simulation)
- [x] CCXTBrokerClient (testnet)
- [x] Live executor (scan → signal → order loop)
- [x] Risk manager (position limits, daily loss limit, circuit breaker)
- [x] Blacklist filter (ST stocks, low liquidity)
- [x] Position tracker
- [x] Daily report generator
- [x] Notification adapters (email, DingTalk, WeChat)
- [x] Self-test: run in simulation mode, verify risk constraints

## Phase 4: Analysis Service & Web Dashboard
- [x] Market overview indicators (breadth, fund flow, fear index)
- [x] BaseLLMService abstract class
- [x] DeepSeek LLM adapter
- [x] News analysis pipeline (clean → analyze → store)
- [x] Auto stock screener
- [x] Buy/sell signal advisor
- [x] FastAPI backend with REST + WebSocket
- [x] Plotly Dash dashboard
  - Overview: equity curve, positions, P&L, risk gauges
  - Strategy: signal flow, performance comparison
  - Backtest: config → run → report visualization
  - AI Analysis: sentiment timeline, word cloud, AI picks
  - Logs: system logs, trade records, alerts
- [x] Self-test: start full system, verify all dashboard panels

## Phase 5: Polish & Extend
- [x] Additional strategies (Panic Reversal, Low Vol Defense) — 7 strategies implemented
- [x] Futures/options contract support — architecture预留 (BrokerClient supports derivatives via leverage config)
- [x] Stress testing & error recovery — tests/test_stress.py with 8 stress tests
- [x] Docker deployment — Dockerfile + docker-compose.yml with Redis + multi-profile
- [x] Complete documentation — README.md with CN/EN docs, inline docstrings, config comments
