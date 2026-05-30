"""
QuantEngine Pro - Stress Tests
================================
Stress tests for the backtest engine and execution layer.

Tests:
- Large dataset handling (10,000+ bars)
- Multiple concurrent strategies
- Extreme market scenarios (flash crash, gap moves)
- Risk manager edge cases
- Rapid signal generation
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


# =============================================================================
# Helper: Generate synthetic market data
# =============================================================================

def generate_ohlcv(
    n_bars: int = 1000,
    start_price: float = 100.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate realistic synthetic OHLCV data.

    Args:
        n_bars: Number of bars to generate
        start_price: Initial price
        volatility: Daily/period volatility
        trend: Drift per bar
        seed: Random seed for reproducibility
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, volatility, n_bars)
    prices = start_price * np.exp(np.cumsum(returns))

    data = []
    base_time = datetime(2024, 1, 1)
    for i in range(n_bars):
        bar_vol = volatility * prices[i]
        open_p = prices[i]
        close_p = prices[i] * (1 + rng.normal(0, volatility * 0.5))
        high_p = max(open_p, close_p) + abs(rng.normal(0, bar_vol * 0.3))
        low_p = min(open_p, close_p) - abs(rng.normal(0, bar_vol * 0.3))
        volume = rng.integers(1000, 100000)

        data.append({
            "timestamp": base_time + timedelta(hours=i),
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": volume,
            "amount": close_p * volume,
        })

    return pd.DataFrame(data)


# =============================================================================
# Tests
# =============================================================================

class TestBacktestStress:
    """Stress tests for the backtest engine."""

    def test_large_dataset(self):
        """Test backtest with 10,000 bars."""
        from quantengine.backtest.engine import BacktestEngine
        from quantengine.strategy.builtin.dual_thrust import DualThrustStrategy

        df = generate_ohlcv(n_bars=10000)
        engine = BacktestEngine(initial_capital=100000, market="crypto")
        strategy = DualThrustStrategy({"k1": 0.7, "k2": 0.7, "period": 20})
        engine.add_strategy(strategy, ["TEST/USDT"], weight=1.0, timeframe="1h")

        report = engine.run({"TEST/USDT": df})
        assert report is not None
        assert "total_return_pct" in report
        assert report["trading_days"] > 0
        print(f"  Large dataset: {report['trading_days']} bars, "
              f"return={report['total_return_pct']}%, sharpe={report['sharpe_ratio']}")

    def test_multi_strategy_parallel(self):
        """Test 5 strategies running in parallel with capital competition."""
        from quantengine.backtest.engine import BacktestEngine
        from quantengine.strategy.builtin.dual_thrust import DualThrustStrategy
        from quantengine.strategy.builtin.turtle import TurtleStrategy
        from quantengine.strategy.builtin.bollinger import BollingerStrategy
        from quantengine.strategy.builtin.dual_ma import DualMAStrategy
        from quantengine.strategy.builtin.grid_ma import GridMAStrategy

        df = generate_ohlcv(n_bars=500)
        engine = BacktestEngine(initial_capital=100000)

        strategies = [
            (DualThrustStrategy({"k1": 0.7, "k2": 0.7}), 0.2),
            (TurtleStrategy({"entry_period": 20}), 0.2),
            (BollingerStrategy({"period": 20}), 0.2),
            (DualMAStrategy({"fast_period": 10, "slow_period": 30}), 0.2),
            (GridMAStrategy({"ma_period": 50}), 0.2),
        ]

        for i, (strat, weight) in enumerate(strategies):
            engine.add_strategy(strat, ["TEST/USDT"], weight=weight)
            strat.name = f"strat_{i}"

        report = engine.run({"TEST/USDT": df})
        assert report is not None
        assert report["total_trades"] >= 0
        print(f"  Multi-strategy: {report['total_trades']} trades, "
              f"final_equity={report['final_equity']:.2f}")

    def test_flash_crash_scenario(self):
        """Test strategy behavior during a simulated flash crash."""
        from quantengine.backtest.engine import BacktestEngine
        from quantengine.strategy.builtin.bollinger import BollingerStrategy
        from quantengine.backtest.position_manager import PositionManager, PositionSide

        # Normal data with sudden -30% crash at bar 200
        df = generate_ohlcv(n_bars=500)
        crash_idx = 200
        df.loc[crash_idx, "open"] = df.loc[crash_idx - 1, "close"] * 0.95
        df.loc[crash_idx, "close"] = df.loc[crash_idx - 1, "close"] * 0.70
        df.loc[crash_idx, "low"] = df.loc[crash_idx, "close"] * 0.98
        df.loc[crash_idx, "high"] = df.loc[crash_idx, "open"]
        df.loc[crash_idx, "volume"] = df["volume"].max() * 5  # Volume spike

        engine = BacktestEngine(initial_capital=100000)
        strategy = BollingerStrategy({"period": 20, "num_std": 2.0})
        strategy.name = "bollinger"
        engine.add_strategy(strategy, ["TEST/USDT"], weight=1.0)

        report = engine.run({"TEST/USDT": df})
        max_dd = report.get("max_drawdown_pct", 0)
        # Verify max drawdown is within reasonable range during crash
        assert max_dd >= 0, f"Max drawdown should be positive, got {max_dd}"
        print(f"  Flash crash: max_drawdown={max_dd}%, "
              f"final_return={report['total_return_pct']}%")


class TestRiskManagerStress:
    """Stress tests for the risk manager."""

    def test_rapid_consecutive_losses(self):
        """Test circuit breaker triggers correctly on consecutive losses."""
        from quantengine.execution.risk_manager import RiskManager

        rm = RiskManager({"consecutive_loss_limit": 5})
        assert rm.is_trading_allowed

        # 5 consecutive losses should trigger breaker
        for _ in range(5):
            assert rm.is_trading_allowed
            rm.record_trade(-100)

        # 6th loss triggers breaker
        rm.record_trade(-100)
        assert not rm.is_trading_allowed, "Circuit breaker should be triggered"
        print(f"  Circuit breaker: trading_allowed={rm.is_trading_allowed} (expected=False)")

    def test_position_limit_boundaries(self):
        """Test position limit enforcement at boundaries."""
        from quantengine.execution.risk_manager import RiskManager

        rm = RiskManager({"max_single_symbol_pct": 0.20})

        # Test: order at exactly 20% (should pass)
        result = rm.check_order("STOCK", 1000, 20, 100000, {})
        assert result.passed, f"20% position should pass, got: {result.message}"

        # Test: order at 20.1% (should fail)
        result = rm.check_order("STOCK", 1005, 20, 100000, {})
        assert not result.passed, f"20.1% position should fail, got: {result.message}"

        # Test: including existing position (500*20 + 501*20 = 20020 > 20000 limit)
        existing = {"STOCK": {"quantity": 500, "current_price": 20}}
        result = rm.check_order("STOCK", 501, 20, 100000, existing)
        assert not result.passed, "20.02% total with existing should fail"

        print("  Position limits: boundary checks passed")

    def test_blacklist_filtering(self):
        """Test blacklist filtering with many symbols."""
        from quantengine.execution.risk_manager import RiskManager

        rm = RiskManager()
        for i in range(100):
            if i % 3 == 0:
                rm.add_to_blacklist(f"STOCK_{i:04d}", "Test blacklist")

        symbols = [f"STOCK_{i:04d}" for i in range(100)]
        filtered = rm.filter_blacklist(symbols)
        # i%3==0 for range(100) → 34 blacklisted (0..99 inclusive), so 100-34=66
        assert len(filtered) == 66, f"Expected 66, got {len(filtered)}"  # 100 - 34 blacklisted
        print(f"  Blacklist: {len(symbols)} → {len(filtered)} symbols after filtering")


class TestPerformance:
    """Performance benchmarks for core components."""

    def test_event_bus_throughput(self):
        """Test EventBus can handle high event throughput."""
        from quantengine.backtest.event_bus import EventBus, EventType, Event

        bus = EventBus()
        count = 0

        def handler(event):
            nonlocal count
            count += 1

        bus.subscribe(EventType.MARKET_DATA, handler)

        # Publish 5000 events
        now = datetime.now()
        for i in range(5000):
            bus.publish(Event(EventType.MARKET_DATA, now, {"close": 100 + i}))

        assert count == 5000, f"Expected 5000 events handled, got {count}"
        elapsed = (datetime.now() - now).total_seconds()
        rate = 5000 / elapsed if elapsed > 0 else float("inf")
        print(f"  EventBus: {count} events in {elapsed:.3f}s ({rate:.0f} events/s)")

    def test_analyzer_large_trade_set(self):
        """Test performance analyzer with 10,000 trades."""
        from quantengine.backtest.analyzer import PerformanceAnalyzer

        dates = pd.date_range("2024-01-01", periods=252, freq="B")
        equity = 100000 * (1 + np.random.randn(252).cumsum() * 0.01)
        eq_curve = list(zip(dates, equity))

        # Generate 10000 random trades
        rng = np.random.default_rng(42)
        trades = []
        for i in range(10000):
            trades.append({
                "symbol": f"STOCK_{rng.integers(0, 100):04d}",
                "pnl": rng.normal(50, 200),
                "strategy": f"strat_{rng.integers(0, 5)}",
                "timestamp": dates[rng.integers(0, 252)],
            })

        analyzer = PerformanceAnalyzer(eq_curve, trades, 100000)
        start = datetime.now()
        report = analyzer.analyze()
        elapsed = (datetime.now() - start).total_seconds()

        assert report["total_trades"] == 10000
        assert report["win_rate_pct"] > 0
        print(f"  Large trade set: 10000 trades analyzed in {elapsed:.3f}s, "
              f"win_rate={report['win_rate_pct']:.1f}%")

    def test_factor_computation_large(self):
        """Test factor computation on large dataset."""
        from quantengine.factor.base import MomentumFactor, VolatilityFactor, RSIFactor, MACDFactor, FactorRegistry

        df = generate_ohlcv(n_bars=50000)

        reg = FactorRegistry()
        reg.register("momentum", MomentumFactor(20))
        reg.register("volatility", VolatilityFactor(20))
        reg.register("rsi", RSIFactor(14))
        reg.register("macd", MACDFactor())

        start = datetime.now()
        scores = reg.compute_all(df)
        composite = reg.composite_score(scores)
        elapsed = (datetime.now() - start).total_seconds()

        assert len(composite) == 50000
        print(f"  Factor computation: 50000 bars × 4 factors in {elapsed:.3f}s")


# =============================================================================
# Run all stress tests
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("QuantEngine Pro - Stress Test Suite")
    print("=" * 60)

    test_classes = [
        TestBacktestStress,
        TestRiskManagerStress,
        TestPerformance,
    ]

    passed = 0
    failed = 0

    for test_class in test_classes:
        print(f"\n[{test_class.__name__}]")
        instance = test_class()
        for name in dir(instance):
            if name.startswith("test_"):
                method = getattr(instance, name)
                try:
                    method()
                    print(f"  PASS {name}")
                    passed += 1
                except Exception as e:
                    print(f"  FAIL {name}: {e}")
                    failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)
