#!/usr/bin/env python3
"""
QuantEngine Pro - Backtest CLI
===============================
Command-line interface for running backtests.

Usage:
    python scripts/run_backtest.py --strategy dual_thrust --symbol ETH/USDT --timeframe 1h
    python scripts/run_backtest.py --strategy turtle --symbol BTC/USDT --timeframe 1d
    python scripts/run_backtest.py --strategy bollinger --symbol ETH/USDT --timeframe 15m
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from quantengine.data.ccxt_fetcher import CCXTQuoteFetcher
from quantengine.strategy.builtin.dual_thrust import DualThrustStrategy
from quantengine.strategy.builtin.turtle import TurtleStrategy
from quantengine.strategy.builtin.bollinger import BollingerStrategy
from quantengine.strategy.builtin.dual_ma import DualMAStrategy
from quantengine.strategy.builtin.r_breaker import RBreakerStrategy
from quantengine.strategy.builtin.grid_ma import GridMAStrategy
from quantengine.strategy.builtin.panic_reversal import PanicReversalStrategy
from quantengine.strategy.builtin.low_vol_defense import LowVolDefenseStrategy
from quantengine.strategy.builtin.aberration import AberrationStrategy
from quantengine.strategy.builtin.pivot_point import PivotPointStrategy
from quantengine.strategy.builtin.fei_ali import FeiAliStrategy
from quantengine.strategy.builtin.dynamic_breakout_ii import DynamicBreakoutIIStrategy
from quantengine.strategy.builtin.rsi_reversal import RSIReversalStrategy
from quantengine.backtest.engine import BacktestEngine

STRATEGY_MAP = {
    "dual_thrust": DualThrustStrategy,
    "turtle": TurtleStrategy,
    "bollinger": BollingerStrategy,
    "dual_ma": DualMAStrategy,
    "r_breaker": RBreakerStrategy,
    "grid_ma": GridMAStrategy,
    "panic_reversal": PanicReversalStrategy,
    "low_vol_defense": LowVolDefenseStrategy,
    "aberration": AberrationStrategy,
    "pivot_point": PivotPointStrategy,
    "fei_ali": FeiAliStrategy,
    "dynamic_breakout_ii": DynamicBreakoutIIStrategy,
    "rsi_reversal": RSIReversalStrategy,
}


async def run_backtest(
    strategy_name: str,
    symbol: str,
    timeframe: str = "1h",
    initial_capital: float = 100000.0,
    market: str = "crypto",
    exchange: str = "binance",
    params: dict = None,
) -> dict:
    """Run a single strategy backtest and return the report."""
    logger.info(f"Running backtest: {strategy_name} on {symbol} ({timeframe})")

    # 1. Fetch data
    if market == "crypto":
        fetcher = CCXTQuoteFetcher({"exchange": exchange})
    else:
        from quantengine.data.akshare_fetcher import AkshareQuoteFetcher
        fetcher = AkshareQuoteFetcher({})

    logger.info(f"Fetching {symbol} {timeframe} data...")
    df = await fetcher.fetch_kline(symbol=symbol, freq=timeframe, limit=1000)

    if df.empty:
        logger.error(f"No data for {symbol}")
        return {"error": "No data available"}

    logger.info(f"Fetched {len(df)} bars: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")

    # 2. Create strategy
    strategy_cls = STRATEGY_MAP.get(strategy_name)
    if strategy_cls is None:
        logger.error(f"Unknown strategy: {strategy_name}")
        return {"error": f"Unknown strategy: {strategy_name}"}

    strategy = strategy_cls(params or {})
    strategy.name = strategy_name

    # 3. Setup engine
    engine = BacktestEngine(initial_capital=initial_capital, market=market)
    engine.add_strategy(strategy=strategy, symbols=[symbol], weight=1.0, timeframe=timeframe)

    # 4. Run
    report = engine.run({symbol: df})

    # 5. Print summary
    print(engine.summary())

    return report


async def main():
    parser = argparse.ArgumentParser(description="QuantEngine Pro - Backtest Runner")
    parser.add_argument("--strategy", choices=list(STRATEGY_MAP.keys()), default="dual_thrust")
    parser.add_argument("--symbol", default="ETH/USDT")
    parser.add_argument("--timeframe", default="1h", choices=["1m","5m","15m","30m","1h","4h","1d"])
    parser.add_argument("--capital", type=float, default=100000.0)
    parser.add_argument("--market", choices=["crypto","a_share"], default="crypto")
    parser.add_argument("--exchange", default="binance")
    args = parser.parse_args()

    report = await run_backtest(
        strategy_name=args.strategy, symbol=args.symbol,
        timeframe=args.timeframe, initial_capital=args.capital,
        market=args.market, exchange=args.exchange,
    )

    if report and "error" not in report:
        logger.info("Backtest completed successfully")
    else:
        logger.error(f"Backtest failed: {report}")


if __name__ == "__main__":
    asyncio.run(main())
