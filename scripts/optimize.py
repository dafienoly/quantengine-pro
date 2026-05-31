#!/usr/bin/env python3
"""
QuantEngine Pro - Strategy Optimizer
======================================
Hyperparameter optimization using Optuna.

Supports multi-objective optimization:
- Maximize Sharpe ratio
- Minimize max drawdown
- Maximize profit factor

Usage:
    python scripts/optimize.py --strategy dual_thrust --symbol ETH/USDT --trials 100
    python scripts/optimize.py --strategy turtle --symbol BTC/USDT --trials 200 --objective sharpe
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
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

# Strategy map with their parameter search spaces
STRATEGY_CONFIG = {
    "dual_thrust": {
        "class": DualThrustStrategy,
        "params": {
            "k1": ("float", 0.3, 1.5),
            "k2": ("float", 0.3, 1.5),
            "period": ("int", 10, 50),
        },
    },
    "turtle": {
        "class": TurtleStrategy,
        "params": {
            "entry_period": ("int", 10, 50),
            "exit_period": ("int", 5, 30),
            "atr_period": ("int", 10, 40),
            "atr_multiplier": ("float", 1.0, 4.0),
        },
    },
    "bollinger": {
        "class": BollingerStrategy,
        "params": {
            "period": ("int", 10, 50),
            "num_std": ("float", 1.0, 3.5),
            "rsi_period": ("int", 7, 28),
            "rsi_oversold": ("int", 15, 45),
            "rsi_overbought": ("int", 55, 85),
        },
    },
    "dual_ma": {
        "class": DualMAStrategy,
        "params": {
            "fast_period": ("int", 5, 50),
            "slow_period": ("int", 30, 150),
            "grid_spacing": ("float", 0.005, 0.05),
            "grid_levels": ("int", 3, 15),
        },
    },
    "r_breaker": {
        "class": RBreakerStrategy,
        "params": {
            "f1": ("float", 0.1, 0.6),
            "f2": ("float", 0.02, 0.2),
            "f3": ("float", 0.1, 0.5),
        },
    },
    "grid_ma": {
        "class": GridMAStrategy,
        "params": {
            "ma_period": ("int", 20, 100),
            "grid_levels": ("int", 5, 20),
            "grid_spacing": ("float", 0.005, 0.05),
            "base_position_pct": ("float", 0.2, 0.8),
        },
    },
    "aberration": {
        "class": AberrationStrategy,
        "params": {
            "period": ("int", 10, 50),
            "num_std": ("float", 1.0, 3.5),
        },
    },
    "pivot_point": {
        "class": PivotPointStrategy,
        "params": {
            "sensitivity": ("categorical", ["conservative", "moderate", "aggressive"]),
        },
    },
    "fei_ali": {
        "class": FeiAliStrategy,
        "params": {
            "atr_mult_sl": ("float", 1.0, 3.0),
            "atr_mult_tp": ("float", 2.0, 5.0),
        },
    },
    "dynamic_breakout_ii": {
        "class": DynamicBreakoutIIStrategy,
        "params": {
            "base_period": ("int", 10, 40),
            "k1": ("float", 0.3, 1.0),
            "k2": ("float", 0.3, 1.0),
        },
    },
    "rsi_reversal": {
        "class": RSIReversalStrategy,
        "params": {
            "rsi_period": ("int", 7, 28),
            "oversold": ("int", 20, 40),
            "overbought": ("int", 60, 80),
        },
    },
    "panic_reversal": {
        "class": PanicReversalStrategy,
        "params": {
            "panic_threshold": ("float", -0.10, -0.02),
            "volume_multiplier": ("float", 1.2, 4.0),
            "stabilization_bars": ("int", 2, 15),
            "rsi_recovery_threshold": ("int", 25, 55),
            "target_recovery_pct": ("float", 0.01, 0.08),
            "stop_loss_pct": ("float", 0.01, 0.05),
        },
    },
    "low_vol_defense": {
        "class": LowVolDefenseStrategy,
        "params": {
            "vol_lookback": ("int", 10, 40),
            "vol_percentile_threshold": ("float", 0.5, 0.95),
            "defense_position_pct": ("float", 0.1, 0.5),
            "rebalance_freq": ("int", 5, 40),
        },
    },
}


class StrategyOptimizer:
    """
    Optuna-based hyperparameter optimizer for trading strategies.

    Usage:
        opt = StrategyOptimizer(strategy_name="dual_thrust", symbol="ETH/USDT")
        best_params, best_score = await opt.optimize(n_trials=100)
    """

    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str = "1h",
        initial_capital: float = 100000.0,
        exchange: str = "binance",
        objective: str = "sharpe",
    ):
        """
        Initialize optimizer.

        Args:
            strategy_name: Strategy to optimize
            symbol: Trading symbol
            timeframe: Bar frequency
            initial_capital: Starting capital
            exchange: Crypto exchange
            objective: 'sharpe', 'calmar', 'profit_factor', or 'composite'
        """
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.exchange = exchange
        self.objective = objective

        if strategy_name not in STRATEGY_CONFIG:
            raise ValueError(
                f"Unknown strategy: {strategy_name}. "
                f"Available: {list(STRATEGY_CONFIG.keys())}"
            )

        self.strategy_config = STRATEGY_CONFIG[strategy_name]
        self._data = None

    async def fetch_data(self):
        """Fetch market data once for all trials."""
        logger.info(f"Fetching {self.symbol} {self.timeframe} data...")
        fetcher = CCXTQuoteFetcher({"exchange": self.exchange})
        self._data = await fetcher.fetch_kline(
            symbol=self.symbol,
            freq=self.timeframe,
            limit=1000,
        )
        if self._data is not None and not self._data.empty:
            logger.info(f"Fetched {len(self._data)} bars")
        else:
            logger.error("Failed to fetch data")

    async def optimize(self, n_trials: int = 100, n_jobs: int = 1) -> tuple:
        """
        Run hyperparameter optimization.

        Args:
            n_trials: Number of optimization trials
            n_jobs: Parallel jobs (1 = sequential)

        Returns:
            Tuple of (best_params_dict, best_objective_score)
        """
        if self._data is None:
            await self.fetch_data()

        if self._data is None or self._data.empty:
            logger.error("No data available for optimization")
            return {}, 0.0

        try:
            import optuna

            logger.info(
                f"Starting optimization: {self.strategy_name} on {self.symbol} "
                f"({n_trials} trials, objective={self.objective})"
            )

            async def objective_fn(trial: optuna.Trial) -> float:
                """Optuna objective function: run backtest with trial params."""
                # Sample parameters from search space
                params = {}
                for name, (ptype, lo, hi) in self.strategy_config["params"].items():
                    if ptype == "float":
                        params[name] = trial.suggest_float(name, lo, hi)
                    elif ptype == "int":
                        params[name] = trial.suggest_int(name, int(lo), int(hi))

                # Create strategy with sampled params
                strategy_cls = self.strategy_config["class"]
                strategy = strategy_cls(params)
                strategy.name = self.strategy_name

                # Run backtest
                engine = BacktestEngine(
                    initial_capital=self.initial_capital,
                    market="crypto",
                )
                engine.add_strategy(
                    strategy=strategy,
                    symbols=[self.symbol],
                    weight=1.0,
                    timeframe=self.timeframe,
                )

                try:
                    report = engine.run({self.symbol: self._data})

                    if "error" in report:
                        return float("-inf")

                    # Calculate objective score
                    sharpe = report.get("sharpe_ratio", 0)
                    max_dd = report.get("max_drawdown_pct", 100) / 100
                    profit_factor = report.get("profit_factor", 0)
                    win_rate = report.get("win_rate_pct", 0) / 100
                    total_return = report.get("total_return_pct", 0) / 100

                    # Clamp to reasonable ranges
                    sharpe = max(min(sharpe, 5.0), -5.0)
                    max_dd = min(abs(max_dd), 0.99)
                    profit_factor = min(profit_factor, 10.0)

                    if self.objective == "sharpe":
                        score = sharpe
                    elif self.objective == "calmar":
                        calmar = (
                            report.get("calmar_ratio", 0)
                            if max_dd > 0 else 0
                        )
                        score = min(calmar, 10.0)
                    elif self.objective == "profit_factor":
                        score = profit_factor
                    elif self.objective == "composite":
                        # Weighted composite: 40% sharpe + 30% return - 20% maxDD + 10% winrate
                        score = (
                            0.4 * sharpe
                            + 0.3 * total_return * 10  # Scale up
                            - 0.2 * max_dd * 5
                            + 0.1 * win_rate * 5
                        )
                    else:
                        score = sharpe

                    # Store metrics in trial
                    trial.set_user_attr("sharpe", sharpe)
                    trial.set_user_attr("max_dd", max_dd)
                    trial.set_user_attr("total_return", total_return)
                    trial.set_user_attr("profit_factor", profit_factor)
                    trial.set_user_attr("trades", report.get("total_trades", 0))

                    return score if not np.isnan(score) else float("-inf")

                except Exception as e:
                    logger.error(f"Trial failed: {e}")
                    return float("-inf")

            # Use Optuna's built-in async optimization
            # Create study with pruner for efficiency
            study = optuna.create_study(
                direction="maximize",
                study_name=f"{self.strategy_name}_{self.symbol}",
                pruner=optuna.pruners.MedianPruner(
                    n_startup_trials=10,
                    n_warmup_steps=5,
                ),
            )

            # Run optimization as sync (optuna doesn't have native async)
            import functools
            loop = asyncio.get_event_loop()

            def _run():
                study.optimize(
                    lambda trial: asyncio.run(objective_fn(trial)),
                    n_trials=n_trials,
                    n_jobs=n_jobs,
                    show_progress_bar=True,
                )

            await loop.run_in_executor(None, _run)

            # Print results
            logger.info("=" * 60)
            logger.info(f"Optimization Complete: {self.strategy_name}")
            logger.info(f"  Best score ({self.objective}): {study.best_value:.4f}")
            logger.info(f"  Best parameters:")
            for name, value in study.best_params.items():
                logger.info(f"    {name}: {value}")
            logger.info(f"  Best trial metrics:")
            for key, value in study.best_trial.user_attrs.items():
                logger.info(f"    {key}: {value}")
            logger.info("=" * 60)

            return study.best_params, study.best_value

        except ImportError:
            logger.error(
                "optuna not installed. Install with: pip install optuna"
            )
            return {}, 0.0


async def main():
    """CLI entry point for strategy optimization."""
    parser = argparse.ArgumentParser(
        description="QuantEngine Pro - Strategy Optimizer (Optuna)"
    )
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGY_CONFIG.keys()),
        default="dual_thrust",
        help="Strategy to optimize",
    )
    parser.add_argument(
        "--symbol",
        default="ETH/USDT",
        help="Trading symbol",
    )
    parser.add_argument("--timeframe", default="1h", help="Bar frequency")
    parser.add_argument("--capital", type=float, default=100000.0, help="Initial capital")
    parser.add_argument("--exchange", default="binance", help="Crypto exchange")
    parser.add_argument(
        "--objective",
        choices=["sharpe", "calmar", "profit_factor", "composite"],
        default="sharpe",
        help="Optimization objective",
    )
    parser.add_argument("--trials", type=int, default=100, help="Number of trials")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel jobs")

    args = parser.parse_args()

    opt = StrategyOptimizer(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_capital=args.capital,
        exchange=args.exchange,
        objective=args.objective,
    )

    best_params, best_score = await opt.optimize(
        n_trials=args.trials,
        n_jobs=args.jobs,
    )

    if best_params:
        logger.info(
            f"\nBest params: {best_params}\n"
            f"Use: python scripts/run_backtest.py --strategy {args.strategy} "
            + " ".join(f"--{k} {v}" for k, v in best_params.items())
        )


if __name__ == "__main__":
    asyncio.run(main())
